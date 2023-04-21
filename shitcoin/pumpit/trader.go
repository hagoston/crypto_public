package main

import (
	"context"
	"errors"
	"strconv"
	"strings"
	"sync"
	"time"

	"go.uber.org/zap"
)

var start_trade_once sync.Once

type Trader struct {
	ctx context.Context
	log *zap.Logger
	kh  *kucoinHandler
	th  *TelegramHandler
	ti  *TraderState // trading info
	chs struct {
		tg_bot_ch          chan string                           // receive/send messages to telegram bot channel
		tg_ann_ch          chan string                           // receive messages from the telegram announcement channel
		sell_prices_ch     chan float64                          // latest sell market match prices
		kh_order_events_ch chan PrivateOrderChangeEventAllFields // channel to receive private trade order changes
		kh_balance_ch      chan string                           // account balance changes
	}
}

const (
	IDLE = iota
	MARKET_BUY_SENT
	MARKET_BUY_DONE
	FAILURE
	END_OF_SHOW
)

type TraderState struct {
	symbol                  string
	symbol_balance          float64
	state                   int     // will be IDLE at the beginning
	market_order_orderid    string  // order of the initial market order
	market_price_avg        float64 // average price from market buy
	highest_sell_price      float64 // initialized to 0, used for trailing stop loss
	new_stop_loss_price     float64 // stop loss price to set (zero after set)
	prev_stop_loss_orederid string  // previous stop loss order
}

func NewTrader(ctx context.Context) *Trader {
	// trader object
	trader := Trader{
		ctx: ctx,
		ti:  &TraderState{},
	}

	// create logger
	trader.log = ConsoleFileLogger()
	defer trader.log.Sync()
	trader.log.Info("started..")

	// make channels
	trader.chs.kh_order_events_ch = make(chan PrivateOrderChangeEventAllFields)
	trader.chs.kh_balance_ch = make(chan string)
	trader.chs.tg_bot_ch = make(chan string) // receive/send messages to telegram bot channel
	trader.chs.tg_ann_ch = make(chan string) // receive messages from the telegram announcement channel
	trader.chs.sell_prices_ch = make(chan float64)

	// kocoin handler
	trader.kh = NewKucoinHandler(trader.log)

	// setup telegram handler
	trader.th = NewTelegramHandler(trader.log, trader.chs.tg_bot_ch, trader.chs.tg_ann_ch)

	// setup python telegram listener writing to the same channel via gRPC
	// note: all message will be received multiple times
	go trader.th.startPythonListeners()

	return &trader
}

func (t *Trader) RunTrader() {
	// !!! save ticker and symbol state
	//t.kh.SaveTickersAndSymbols()

	// kucoin private order change websocket listener
	go t.kh.PrivateTradeOrderesWebsocketFeed(t.chs.kh_order_events_ch, t.chs.kh_balance_ch)

	// run telegram
	go t.th.Run(t.ctx)

	// stop loss update every 100ms at most
	sl_ticker := time.NewTicker(100 * time.Millisecond)
	defer sl_ticker.Stop()

	// main loop: process channel messages
	for {
		select {
		case bot_msg := <-t.chs.tg_bot_ch:
			// control message from bot channel
			t.log.Info("bot msg received", zap.String("msg", bot_msg))
			// echo
			t.chs.tg_bot_ch <- "[echo] " + bot_msg
		case ann_msg := <-t.chs.tg_ann_ch:
			// announcement message to start pumping
			coin_symbol, err := getCoinSymbolFromAnnouncementMsg(ann_msg)
			if err != nil {
				t.log.Info("announcement msg: " + ann_msg)
				// t.log.Error("failed to parce announcement message")
				continue
			}
			t.log.Info("valid announcement msg received", zap.String("coin_symbol", coin_symbol))
			// check coin_symbol-USDT pair
			symbol := coin_symbol + "-USDT"
			if symbol_ticker, exists := t.kh.tickers[symbol]; exists {
				t.log.Info("valid symbol", zap.Any("ticker", symbol_ticker), zap.Any("symbol", t.kh.symbols[symbol]))
				// start trading process
				start_trade_once.Do(func() {
					t.ti.symbol = symbol
					t.startTrading()
				})
			} else {
				t.log.Error("invalid ticker")
			}
		case oe := <-t.chs.kh_order_events_ch:
			// kucoin personal order change events
			t.log.Info("order_event", zap.Any("", oe))

			// waiting for market buy success
			if t.ti.state == MARKET_BUY_SENT {
				if t.ti.market_order_orderid == oe.OrderId {
					if oe.Status == "done" && oe.Type == "canceled" {
						// market buy finished or canceled
						if oe.FilledSize == "0" {
							// canceled
							t.log.Error("market buy canceled")
							t.ti.state = FAILURE
						} else {
							// calculate average price
							if filled_size, err := strconv.ParseFloat(oe.FilledSize, 64); err == nil {
								t.ti.market_price_avg = t.kh.cred.Market_price_buy_usdt / filled_size
								t.log.Info("market buy done", zap.Float64("t.ti.market_price_avg", t.ti.market_price_avg))
								t.ti.state = MARKET_BUY_DONE
							} else {
								t.log.Error("filled size conversion failed")
								t.ti.state = FAILURE
							}
						}
					}
				}
			}
		case sell_price := <-t.chs.sell_prices_ch:
			//t.log.Info("sell price received", zap.Float64("sell_price", sell_price))
			// save if grater than previous, set trailing stop-loss with it
			if t.ti.state == END_OF_SHOW {
				t.log.Info("END_OF_SHOW highest_sell_price sell price update", zap.Float64("sell_price", sell_price))
				continue
			}
			if t.ti.highest_sell_price < sell_price {
				t.log.Info("highest_sell_price sell price update", zap.Float64("sell_price", sell_price))
				// calc stop loss
				t.ti.new_stop_loss_price = sell_price * (1 - t.kh.cred.Trailing_stop_loss_percentage/100)
				t.ti.highest_sell_price = sell_price
			}
		case account_balance := <-t.chs.kh_balance_ch:
			// account_balance e.g. "USDT:32.7101595826388"
			account_balace_parts := strings.Split(account_balance, ":")
			account_currency := account_balace_parts[0]
			trading_currency := strings.Split(t.ti.symbol, "-USDT")[0]

			if account_currency == trading_currency {
				if balance, err := strconv.ParseFloat(account_balace_parts[1], 64); err == nil {
					t.ti.symbol_balance = balance
					t.log.Info("trading currency balance update", zap.String("currency", account_currency), zap.Float64("balance", balance))

					if t.ti.symbol_balance <= 0 {
						// end of show
						t.log.Info("end of show")
						t.ti.state = END_OF_SHOW
					}
				}
			}
		case <-sl_ticker.C:
			// stop loss setup
			if t.ti.state == MARKET_BUY_DONE && t.ti.new_stop_loss_price > 0 {
				prev_stop_loss_orederid := t.kh.StopLossOrder(t.ti.symbol, t.ti.new_stop_loss_price, t.ti.symbol_balance)
				if t.ti.prev_stop_loss_orederid != "" {
					t.kh.CancelOrder(t.ti.prev_stop_loss_orederid)
				}
				t.ti.prev_stop_loss_orederid = prev_stop_loss_orederid
				t.ti.new_stop_loss_price = 0
			}
		}
	}
}

func getCoinSymbolFromAnnouncementMsg(msg string) (string, error) {
	parts := strings.Split(msg, "kucoin.com/trade/")
	if len(parts) != 2 {
		return "", errors.New("kucoin.com/trade/ delimiter not found")
	}
	parts = strings.Split(parts[1], "-USDT")
	if len(parts) != 2 {
		return "", errors.New("-USDT delimiter not found")
	}
	return parts[0], nil
}

func (t *Trader) startTrading() {
	t.log.Info("############# START TRADING #############")

	// subscribe to ticker data
	go t.kh.MatchWebsocketFeed(t.ti.symbol, t.chs.sell_prices_ch)
	go t.kh.TickerWebsocketFeed(t.ti.symbol)
	t.log.Info("ticker websocket listener started")

	// buy with market price
	t.ti.market_order_orderid = t.kh.InitialMarketOrder(t.ti.symbol)
	if t.ti.market_order_orderid == "" {
		t.log.Error("empty orderid ")
		t.ti.state = FAILURE
	} else {
		t.ti.state = MARKET_BUY_SENT
	}
}
