package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"sync"
)

var secret Secret
var once_secret sync.Once

type Secret struct {
	Market_price_buy_usdt         float64 `json:"market_price_buy_usdt"`
	Trailing_stop_loss_percentage float64 `json:"trailing_stop_loss_percentage"`
	Grpc_port                     string  `json:"grpc_port"`
	Tg_announcement_channel_name  string  `json:"tg_announcement_channel_name"`
	Tg_bot_channel_name           string  `json:"tg_bot_channel_name"`
	Kc_key                        string  `json:"kc_key"`
	Kc_secret                     string  `json:"kc_secret"`
	Kc_passphrase                 string  `json:"kc_passphrase"`
	Tg_bot_token                  string  `json:"tg_bot_token"`
	Tg_api_id                     int     `json:"tg_api_id"`
	Tg_api_hash                   string  `json:"tg_api_hash"`
	Telephone                     string  `json:"telephone"`
}

func (s *Secret) init() {
	file, err := os.Open("./secrets.json")
	if err != nil {
		fmt.Println("credentials file not found (./secrets.json)")
		return
	}
	defer file.Close()

	byteResult, _ := io.ReadAll(file)
	json.Unmarshal([]byte(byteResult), &secret)
}

func NewSecret() *Secret {
	once_secret.Do(secret.init)
	return &secret
}
