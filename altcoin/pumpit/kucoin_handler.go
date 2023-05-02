package main

import (
	"encoding/json"
	"io/ioutil"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/Kucoin/kucoin-go-sdk"
	"go.uber.org/zap"
)

const TICKERS_SYMBOLS_FOLDER_NAME string = "./tickers_symbols"

type kucoinHandler struct {
	log     *zap.Logger
	conn    *kucoin.ApiService
	cred    *Secret
	tickers map[string]*kucoin.TickerModel // map[symbol]*kucoin.TickerModel
	symbols map[string]*kucoin.SymbolModel
}

func NewKucoinHandler(logger *zap.Logger) *kucoinHandler {
	kh := kucoinHandler{
		log: logger,
	}
	kh.cred = NewSecret()
	kh.conn = kucoin.NewApiService(
		// kucoin.ApiBaseURIOption("https://api.kucoin.com"),
		kucoin.ApiKeyOption(kh.cred.Kc_key),
		kucoin.ApiSecretOption(kh.cred.Kc_secret),
		kucoin.ApiPassPhraseOption(kh.cred.Kc_passphrase),
	)

	// load tickers from file
	ticker_file, err := getLastFileFromDir(TICKERS_SYMBOLS_FOLDER_NAME)
	if err != nil {
		// save ticker and symbol cause not found
		kh.SaveTickersAndSymbols()
		// read again
		ticker_file, err = getLastFileFromDir(TICKERS_SYMBOLS_FOLDER_NAME)
		if err != nil {
			kh.log.Error(err.Error())
		}
	}
	kh.LoadTickersSymbolsFromFile(ticker_file)

	// server time into log
	kh.PrintServerTime()

	return &kh
}

func (kh *kucoinHandler) InitialMarketOrder(symbol string) string {
	/*
		SYMBOL example
			"symbol": "GALAX-USDT",
			"name": "GALA-USDT",
			"baseCurrency": "GALAX",
			"quoteCurrency": "USDT",

		MARKET ORDER PARAMETERS
			Param	type	Description
			size	String	[Optional] Desired amount in base currency
			funds	String	[Optional] The desired amount of quote currency to use
			It is required that you use one of the two parameters, size or funds.
	*/
	p := &kucoin.CreateOrderModel{
		ClientOid: kucoin.IntToString(time.Now().UnixNano()),
		Side:      "buy",
		Symbol:    symbol,
		Type:      "market",
		Funds:     strconv.FormatFloat(float64(kh.cred.Market_price_buy_usdt), 'f', 0, 64),
	}
	rsp, err := kh.conn.CreateOrder(p)
	if err != nil {
		kh.log.Error(err.Error())
		return ""
	}
	o := &kucoin.CreateOrderResultModel{}
	if err := rsp.ReadData(o); err != nil {
		kh.log.Error(err.Error())
		return ""
	}
	kh.log.Info("initial market order sent",
		zap.String("usdt", p.Funds),
		zap.String("OrderId", o.OrderId),
		zap.String("ClientOid", p.ClientOid),
		zap.String("Symbol", p.Symbol))
	return o.OrderId
}

func (kh *kucoinHandler) PriceToString(symbol string, price float64) string {
	pi := kh.symbols[symbol].PriceIncrement
	decimals := len(pi) - 2
	return strconv.FormatFloat(float64(price), 'f', decimals, 64)
}

func (kh *kucoinHandler) BaseSizeToString(symbol string, size float64) string {
	bi := kh.symbols[symbol].BaseIncrement
	decimals := len(bi) - 2
	return strconv.FormatFloat(float64(size), 'f', decimals, 64)
}

func (kh *kucoinHandler) StopLossOrder(symbol string, stop_loss_price float64, size float64) string {

	stop_loss_price_str := kh.PriceToString(symbol, stop_loss_price)
	size_str := kh.BaseSizeToString(symbol, size)

	p := &kucoin.CreateOrderModel{
		ClientOid: kucoin.IntToString(time.Now().UnixNano()),
		Side:      "sell",
		Symbol:    symbol,
		Type:      "market",
		Stop:      "loss",
		StopPrice: stop_loss_price_str,
		Size:      size_str,
	}
	rsp, err := kh.conn.CreateStopOrder(p)
	if err != nil {
		kh.log.Error(err.Error())
		return ""
	}
	o := &kucoin.CreateOrderResultModel{}
	if err := rsp.ReadData(o); err != nil {
		kh.log.Error(err.Error())
		return ""
	}
	kh.log.Info("sl set", zap.Any("order", p))

	return o.OrderId
}

func (kh *kucoinHandler) CancelOrder(order_id string) {

	rsp, err := kh.conn.CancelOrder(order_id)
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	o := &kucoin.CancelOrderResultModel{}
	if err := rsp.ReadData(o); err != nil {
		kh.log.Error(err.Error())
		return
	}
	kh.log.Info("cancer order", zap.Any("order", o))
}

func getLastFileFromDir(dirPath string) (string, error) {
	files, err := ioutil.ReadDir(dirPath)
	if err != nil {
		return "", err
	}

	var fileNames []string
	for _, file := range files {
		fileNames = append(fileNames, file.Name())
	}

	sort.Strings(fileNames)
	lastFile := fileNames[len(fileNames)-1]
	return filepath.Join(dirPath, lastFile), nil
}

func (kh *kucoinHandler) PrintServerTime() error {
	rsp, err := kh.conn.ServerTime()
	if err != nil {
		return err
	}

	var ts int64
	if err := rsp.ReadData(&ts); err != nil {
		return err
	}
	kh.log.Info("kucoin server time", zap.Int64("count", ts))
	return nil
}

func (kh *kucoinHandler) GetFlatPrices() {
	prices, err := kh.conn.Prices("", "")
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	price_model := kucoin.PricesModel{}
	if err := prices.ReadData(&price_model); err != nil {
		kh.log.Error(err.Error())
		return
	}
	for base, currency := range price_model {
		kh.log.Info("Available prices",
			zap.String("base", base),
			zap.String("price", currency))
	}

}

func (kh *kucoinHandler) LoadTickersSymbolsFromFile(fname string) {
	jsonFile, err := os.Open(fname)
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	defer jsonFile.Close()

	jsonData, err := ioutil.ReadAll(jsonFile)
	if err != nil {
		kh.log.Error(err.Error())
		return
	}

	var tickers kucoin.TickersModel
	json.Unmarshal(jsonData, &tickers)
	// convert into map
	kh.tickers = map[string]*kucoin.TickerModel{}
	for _, ticker := range tickers {
		kh.tickers[ticker.Symbol] = ticker
	}

	// load symbols
	parts := strings.Split(fname, "_tickers.json")
	jsonFile, err = os.Open(parts[0] + "_symbols.json")
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	defer jsonFile.Close()
	jsonData, err = ioutil.ReadAll(jsonFile)
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	var symbols kucoin.SymbolsModel
	json.Unmarshal(jsonData, &symbols)
	// convert into map
	kh.symbols = map[string]*kucoin.SymbolModel{}
	for _, symbol := range symbols {
		kh.symbols[symbol.Symbol] = symbol
	}
}

func (kh *kucoinHandler) SaveTickersAndSymbols() {
	rsp, err := kh.conn.Tickers()
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	tickers_resp_model := kucoin.TickersResponseModel{}
	if err := rsp.ReadData(&tickers_resp_model); err != nil {
		kh.log.Error(err.Error())
		return
	}
	// save tickers into file
	jsonData, err := json.MarshalIndent(tickers_resp_model.Tickers, "", "  ")
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	// file name
	tickers_time := tickers_resp_model.Time
	file_name := kucoin.IntToString(tickers_time) + "_tickers.json"
	file_path := filepath.Join(TICKERS_SYMBOLS_FOLDER_NAME)
	tickers_file := filepath.Join(file_path, file_name)
	if _, err := os.Stat(tickers_file); os.IsNotExist(err) {
		os.MkdirAll(file_path, os.ModePerm)
	}
	file, err := os.Create(tickers_file)
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	defer file.Close()
	// write
	_, err = file.Write(jsonData)
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	kh.log.Info("tickers wrote into file", zap.String("file_name", file_name))

	// --------------- now the symbols
	rsp, err = kh.conn.Symbols("USDS")
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	sm := kucoin.SymbolsModel{}
	if err := rsp.ReadData(&sm); err != nil {
		kh.log.Error(err.Error())
		return
	}
	jsonData, err = json.MarshalIndent(sm, "", "  ")
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	file_name = kucoin.IntToString(tickers_time) + "_symbols.json"
	symbols_file := filepath.Join(file_path, file_name)
	file, err = os.Create(symbols_file)
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	defer file.Close()
	_, err = file.Write(jsonData)
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	kh.log.Info("symbols wrote into file", zap.String("file_name", file_name))

}

func (kh *kucoinHandler) Accounts() {
	rsp, err := kh.conn.Accounts("", "")
	if err != nil {
		kh.log.Error(err.Error())
		return
	}

	as := kucoin.AccountsModel{}
	if err := rsp.ReadData(&as); err != nil {
		kh.log.Error(err.Error())
		return
	}

	for _, a := range as {
		kh.log.Info("Available balance",
			zap.String("Type", a.Type),
			zap.String("Currency", a.Currency),
			zap.String("Available", a.Available))
	}
}

func (kh *kucoinHandler) PrivateTradeOrderesWebsocketFeed(
	kc_events_ch chan<- PrivateOrderChangeEventAllFields,
	kc_balance_ch chan<- string) {
	rsp, err := kh.conn.WebSocketPrivateToken()
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	tk := &kucoin.WebSocketTokenModel{}
	if err := rsp.ReadData(tk); err != nil {
		kh.log.Error(err.Error())
		return
	}
	c := kh.conn.NewWebSocketClient(tk)
	mc, ec, err := c.Connect()
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	defer c.Stop()

	ch1 := kucoin.NewSubscribeMessage("/spotMarket/tradeOrders", true)
	ch2 := kucoin.NewSubscribeMessage("/account/balance", true)
	if err := c.Subscribe(ch1, ch2); err != nil {
		kh.log.Error(err.Error())
		return
	}

	for {
		select {
		case err := <-ec:
			kh.log.Error(err.Error())
			return

		case msg := <-mc:
			topic := msg.Topic
			// subject := msg.Subject

			if topic == "/spotMarket/tradeOrders" {
				var msg_data PrivateOrderChangeEventAllFields
				if err := msg.ReadData(&msg_data); err != nil {
					kh.log.Error("Failed to parse specific msg", zap.String("error", err.Error()))
					return
				}
				// send received event message
				kh.log.Info("OrderChangeEvent", zap.Any("event", msg_data))
				kc_events_ch <- msg_data
			} else if topic == "/account/balance" {
				var msg_data AccountBalanceData
				if err := msg.ReadData(&msg_data); err != nil {
					kh.log.Error("Failed to parse specific msg", zap.String("error", err.Error()))
					return
				}
				kh.log.Info("AccountBalanceData", zap.Any("event", msg_data))
				kc_balance_ch <- msg_data.Currency + ":" + msg_data.Available
			}
		}
	}
}

func (kh *kucoinHandler) Level2MarketData(symbol string) {
	log := MinimalFileLogger(symbol + "_l2")
	defer log.Sync()

	rsp, err := kh.conn.WebSocketPublicToken()
	if err != nil {
		kh.log.Error(err.Error())
		return
	}

	tk := &kucoin.WebSocketTokenModel{}
	if err := rsp.ReadData(tk); err != nil {
		kh.log.Error(err.Error())
		return
	}

	c := kh.conn.NewWebSocketClient(tk)

	mc, ec, err := c.Connect()
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	defer c.Stop()

	ch := kucoin.NewSubscribeMessage("/market/level2:"+symbol, false)
	if err := c.Subscribe(ch); err != nil {
		kh.log.Error(err.Error())
		return
	}

	for {
		select {
		case err := <-ec:
			c.Stop() // Stop subscribing the WebSocket feed
			kh.log.Error(err.Error())
			return
		case msg := <-mc:
			log.Error(msg.Topic)
		}
	}
}

func (kh *kucoinHandler) TickerWebsocketFeed(symbol string) {
	log := MinimalFileLogger(symbol + "_ticker")
	defer log.Sync()

	rsp, err := kh.conn.WebSocketPublicToken()
	if err != nil {
		kh.log.Error(err.Error())
		return
	}

	tk := &kucoin.WebSocketTokenModel{}
	if err := rsp.ReadData(tk); err != nil {
		kh.log.Error(err.Error())
		return
	}

	c := kh.conn.NewWebSocketClient(tk)

	mc, ec, err := c.Connect()
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	defer c.Stop()

	ch := kucoin.NewSubscribeMessage("/market/ticker:"+symbol, false)
	if err := c.Subscribe(ch); err != nil {
		kh.log.Error(err.Error())
		return
	}

	for {
		select {
		case err := <-ec:
			c.Stop() // Stop subscribing the WebSocket feed
			kh.log.Error(err.Error())
			return
		case msg := <-mc:
			t := &kucoin.TickerLevel1Model{}
			if err := msg.ReadData(t); err != nil {
				kh.log.Error("Failure to read:", zap.String("err msg", err.Error()))
				return
			}

			log.Info("ticker", zap.Any("fields", t))
			/*
				log.Info("Ticker",
					//zap.String("topic", msg.Topic),
					zap.Int64("time", t.Time),
					zap.String("sequence", t.Sequence),
					zap.String("price", t.Price),
					zap.String("size", t.Size),
					zap.String("bb", t.BestBid),
					zap.String("bbs", t.BestBidSize),
					zap.String("ba", t.BestAsk),
					zap.String("bas", t.BestAskSize),
				)
			*/
		}
	}
}

func (kh *kucoinHandler) MatchWebsocketFeed(symbol string, sell_price_ch chan<- float64) {
	log := MinimalFileLogger(symbol + "_match")
	defer log.Sync()
	rsp, err := kh.conn.WebSocketPublicToken()
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	tk := &kucoin.WebSocketTokenModel{}
	if err := rsp.ReadData(tk); err != nil {
		kh.log.Error(err.Error())
		return
	}
	c := kh.conn.NewWebSocketClient(tk)

	mc, ec, err := c.Connect()
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	defer c.Stop()

	ch := kucoin.NewSubscribeMessage("/market/match:"+symbol, false)
	if err := c.Subscribe(ch); err != nil {
		kh.log.Error(err.Error())
		return
	}

	type MarketMatchModel struct {
		Sequence     string `json:"sequence"`
		Type         string `json:"type"`
		Symbol       string `json:"symbol"`
		Side         string `json:"side"`
		Price        string `json:"price"`
		Size         string `json:"size"`
		TradeId      string `json:"tradeId"`
		TakerOrderId string `json:"takerOrderId"`
		MakerOrderId string `json:"makerOrderId"`
		Time         string `json:"time"`
	}

	for {
		select {
		case err := <-ec:
			c.Stop()
			kh.log.Error(err.Error())
			return
		case msg := <-mc:
			t := &MarketMatchModel{}
			if err := msg.ReadData(t); err != nil {
				kh.log.Error("Failure to read:", zap.String("err msg", err.Error()))
				return
			}
			log.Info("match", zap.Any("fields", t))
			if t.Side == "sell" {
				if price, err := strconv.ParseFloat(t.Price, 64); err == nil {
					sell_price_ch <- price
				}
			}
		}
	}
}
