package main

import (
	"context"
	"encoding/hex"
	"fmt"
	"log"
	"math/big"
	"os"
	"regexp"
	"time"

	"github.com/ethereum/go-ethereum/ethclient"
)

const MAX_PARALLEL_BLOCK_GOROUTINE = 50

func main() {
	// start block getter
	current_t := time.Now()
	f_name := "./BNB_" + current_t.Format("20060102_150405") + ".txt"
	fmt.Printf("new file %s created\n", f_name)
	f, err := os.Create(f_name)
	if err != nil {
		log.Fatal(err)
	}

	fmt.Printf("STARING...\n")
	c := block_req(21490000, -1)

	for msg := range c {
		fmt.Printf("%q\n", msg)
		f.WriteString(msg + "\n")
	}
}

func block_req(start_block int64, end_block int64) <-chan string {
	// connect to local RPC
	client, err := ethclient.Dial("https://bsc-dataseed1.binance.org") // local BSC
	// client, err := ethclient.Dial("https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161") // ETH
	// client, err := ethclient.Dial("https://rpc.ftm.tools") // FANTOM
	// client, err := ethclient.Dial("https://polygon-rpc.com") // MATIC
	if err != nil {
		log.Fatal(err)
	}

	// output channel with interesting contract addresses
	c := make(chan string)
	// goroutine limiter
	limiter := make(chan bool, MAX_PARALLEL_BLOCK_GOROUTINE)

	start := time.Now()
	go func() {
		block_num := start_block
		is_end_latest := end_block < 0

		for {
			if is_end_latest {
				header, err := client.HeaderByNumber(context.Background(), nil)
				if err != nil {
					log.Fatal(err)
				}
				end_block = header.Number.Int64()
				fmt.Printf("latest block updated to %d\n", end_block)
				if block_num >= end_block {
					// latest block reached, exit
					break
				}
			}

			for ; block_num < end_block+1; block_num++ {
				investigate_block(client, block_num, c, limiter, 0)

				// some time log
				if block_num%1000 == 0 {
					elapsed := time.Since(start)
					start = time.Now()
					percentage := float32(block_num-start_block) / float32(end_block-start_block) * 100.0
					fmt.Printf("%.2f%% #%d %s\n", percentage, block_num, elapsed)
				}
			}

			if !is_end_latest {
				break
			}
		}
		fmt.Printf("[%d .. %d] -- FINISHED\n", start_block, end_block)
		close(c)
	}()

	// return the channel to the caller
	return c
}

func investigate_block(client *ethclient.Client, block_num int64, result_ch chan string, limiter_ch chan bool, recursion int8) {

	// contract string to looking for
	var re = regexp.MustCompile(`3243c791|03c83302|6a474002|a493a922|64b0f653|a8b9d240|e7841ec0|ad56c13c`)
	limiter_ch <- true

	go func(block_num int64) {
		// block number
		block_num_ := big.NewInt(block_num)

		// get block
		block, _ := client.BlockByNumber(context.Background(), block_num_)

		if block == nil {
			// max retry 5 recursion
			if recursion > 5 {
				fmt.Printf("ERROR|%d block missed\n", block_num_)
				return
			} else {
				// retry after some sleep
				fmt.Printf("INFO|#%d retry no %d\n", block_num_, recursion)
				time.Sleep(100 * time.Millisecond)
				investigate_block(client, block_num, result_ch, limiter_ch, recursion+1)
			}
		}

		// fmt.Println(block_num_, len(block.Transactions()))
		// iterate through txs
		for _, tx := range block.Transactions() {
			// empty 'to' means contract creation
			if tx.To() == nil {
				// convert byte array to hex string
				data := hex.EncodeToString(tx.Data())

				// check encoded function arguments
				if re.MatchString(data) {
					// check receipt for status
					receipt, err := client.TransactionReceipt(context.Background(), tx.Hash())
					if err != nil {
						log.Fatal(err)
					}

					if receipt.Status == 1 {
						// status ok, send contract address into channel
						result := fmt.Sprintf("%d, %s", block_num, receipt.ContractAddress.Hex())
						result_ch <- result
					}
				}
			}
		}
		// removes one element from limiter, allowing another to proceed
		<-limiter_ch
	}(block_num)
}

func parallel_block_req_test() {
	client, err := ethclient.Dial("http://192.168.100.88:8545")
	if err != nil {
		log.Fatal(err)
	}

	start := time.Now()

	tx_cnts := make(chan int)
	block_start := int64(5671744)
	block_range := int64(1000)

	for block_num := block_start; block_num < block_start+block_range; block_num++ {
		go func(block_num int64) {
			bln := big.NewInt(block_num)
			// fmt.Println(bln)
			block, _ := client.BlockByNumber(context.Background(), bln)
			tx_cnts <- len(block.Transactions())
		}(block_num)
	}

	var tx_cnt_sum int = 0
	for i := 0; i < int(block_range); i++ {
		tx_cnt_sum += <-tx_cnts
	}
	fmt.Println(tx_cnt_sum)

	elapsed := time.Since(start)
	log.Printf("Binomial took %s", elapsed)

	close(tx_cnts)
}
