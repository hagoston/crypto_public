package main

type RelationContextData struct {
	Symbol  string `json:"symbol"`
	TradeId string `json:"tradeId"`
	OrderId string `json:"orderId"`
}

type AccountBalanceData struct {
	Total           string              `json:"total"`
	Available       string              `json:"available"`
	AvailableChange string              `json:"availableChange"`
	Currency        string              `json:"currency"`
	Hold            string              `json:"hold"`
	HoldChange      string              `json:"holdChange"`
	RelationEvent   string              `json:"relationEvent"`
	RelationEventId string              `json:"relationEventId"`
	RelationContext RelationContextData `json:"relationContext"`
	Time            string              `json:"time"`
}

type PrivateOrderChangeEvent struct {
	Symbol     string `json:"symbol"`
	OrderType  string `json:"orderType"`
	Side       string `json:"side"`
	OrderId    string `json:"orderId"`
	Type       string `json:"type"`
	OrderTime  int64  `json:"orderTime"`
	Size       string `json:"size"`
	FilledSize string `json:"filledSize"`
	Price      string `json:"price"`
	ClientOid  string `json:"clientOid"`
	RemainSize string `json:"remainSize"`
	Status     string `json:"status"`
	Ts         int64  `json:"ts"`
}

type PrivateOrderChangeEventAllFields struct {
	Symbol     string `json:"symbol"`
	OrderType  string `json:"orderType"`
	Side       string `json:"side"`
	OrderId    string `json:"orderId"`
	Type       string `json:"type"`
	OrderTime  int64  `json:"orderTime"`
	Size       string `json:"size"`
	FilledSize string `json:"filledSize"`
	Price      string `json:"price"`
	ClientOid  string `json:"clientOid"`
	RemainSize string `json:"remainSize"`
	Status     string `json:"status"`
	Ts         int64  `json:"ts"`
	Liquidity  string `json:"liquidity"`
	MatchPrice string `json:"matchPrice"`
	MatchSize  string `json:"matchSize"`
	TradeId    string `json:"tradeId"`
	OldSize    string `json:"oldSize"`
}

type PrivateOrderChangeEvent_Open = PrivateOrderChangeEvent
type PrivateOrderChangeEvent_Filled = PrivateOrderChangeEvent
type PrivateOrderChangeEvent_Caceled = PrivateOrderChangeEvent

type PrivateOrderChangeEvent_Match struct {
	PrivateOrderChangeEvent
	Liquidity  string `json:"liquidity"`
	MatchPrice string `json:"matchPrice"`
	MatchSize  string `json:"matchSize"`
	TradeId    string `json:"tradeId"`
}

type PrivateOrderChangeEvent_Update struct {
	PrivateOrderChangeEvent
	OldSize string `json:"oldSize"`
}
