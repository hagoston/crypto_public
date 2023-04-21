package main

import (
	"context"
	"errors"
	"os"
	"os/signal"
	"syscall"
)

func main() {
	// make sure defer-s are called with panicing for ctrl+c
	sigCh := make(chan os.Signal)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM, syscall.SIGKILL, syscall.SIGINT)
	go func() {
		select {
		case <-sigCh:
			panic(errors.New("intended panic exit"))
		}
	}()

	trader()
}

func trader() {
	// context
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	trader := NewTrader(ctx)
	// run telegram
	trader.RunTrader()
}

func kline_download() {
	log := ConsoleFileLogger()
	defer log.Sync()

	// kocoin handler
	kh := NewKucoinHandler(log)

	// downloader

	symbol := "ARKER-USDT"
	pump_time := "2022-11-06T17:00:00"

	if true {
		symbol = "LAVAX-USDT"
		pump_time = "2022-10-23T16:00:00"
	}
	if false {
		symbol = "FLAME-USDT"
		pump_time = "2022-10-16T16:00:00"
	}

	kline_type := "1min"
	pump_unix_time := str2time(pump_time)

	start_time := time2str(pump_unix_time - day2sec(1))
	end_time := time2str(pump_unix_time + day2sec(1))

	kh.GetKlines(symbol, kline_type, start_time, end_time)
}
