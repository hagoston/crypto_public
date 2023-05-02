package main

import (
	"encoding/csv"
	"os"
	"time"

	"github.com/Kucoin/kucoin-go-sdk"
)

func str2time(time_str string) int64 {
	t, _ := time.Parse("2006-01-02T15:04:05", time_str)
	return t.Unix()
}

func time2str(time_unix int64) string {
	return time.Unix(time_unix, 0).UTC().Format("2006-01-02T15:04:05")
}

func day2sec(number_of_days int64) int64 {
	return number_of_days * 24 * 60 * 60
}

type Kline struct {
	time     string //Start time of the candle cycle
	open     string //opening price
	close    string //closing price
	high     string //highest price
	low      string //lowest price
	volume   string //Transaction volume
	turnover string //Transaction amount
}

func (kh *kucoinHandler) GetKlines(symbol string, kline_type string, start_time string, end_time string) {
	// kline_type := 1min, 3min, 5min, 15min, 30min, 1hour, 2hour, 4hour, 6hour, 8hour, 12hour, 1day, 1week
	start_time_i64 := str2time(start_time)
	end_time_i64 := str2time(end_time)
	rsp, err := kh.conn.KLines(symbol, kline_type, start_time_i64, end_time_i64)
	if err != nil {
		kh.log.Error(err.Error())
		return
	}

	ksm := kucoin.KLinesModel{}
	if err := rsp.ReadData(&ksm); err != nil {
		kh.log.Error(err.Error())
		return
	}

	file, err := os.Create(symbol + "_" + kline_type + "_klines.csv")
	if err != nil {
		kh.log.Error(err.Error())
		return
	}
	defer file.Close()
	w := csv.NewWriter(file)
	defer w.Flush()

	header := []string{"Time", "Open", "Close", "High", "Low", "Volume", "Turnover"}
	err = w.Write(header)
	if err != nil {
		kh.log.Error(err.Error())
	}

	for _, record := range ksm {
		if err := w.Write(*record); err != nil {
			kh.log.Error(err.Error())
		}
	}

}
