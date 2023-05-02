package main

import (
	"bufio"
	"context"
	"fmt"
	"net"
	"os"
	"os/exec"
	"strings"
	"time"

	pb "crypto/shitcoin/pumpit/grpc/server/message" // gRPC messaging

	"go.uber.org/zap"

	"github.com/gotd/td/session"
	"github.com/gotd/td/telegram"
	"github.com/gotd/td/telegram/auth"
	"github.com/gotd/td/telegram/message"
	"github.com/gotd/td/tg"
	"google.golang.org/grpc"
)

type TelegramHandler struct {
	log       *zap.Logger
	tg_bot_ch chan string
	tg_ann_ch chan<- string
	cred      *Secret
}

func NewTelegramHandler(logger *zap.Logger, tg_bot_ch chan string, tg_ann_ch chan<- string) *TelegramHandler {
	cred := NewSecret()
	th := TelegramHandler{
		log:       logger,
		tg_bot_ch: tg_bot_ch,
		tg_ann_ch: tg_ann_ch,
		cred:      cred,
	}
	return &th
}

func (th TelegramHandler) newMessage(ctx context.Context, e tg.Entities, update *tg.UpdateNewMessage) error {
	m, ok := update.Message.(*tg.Message)
	if !ok || !m.Out {
		// outgoing message, not interesting
		return nil
	}
	// fw bot message
	th.tg_bot_ch <- m.GetMessage()
	th.log.Info("tg rx", zap.Any("tg_bot_ch", m.GetMessage()))
	return nil
}

// python gRPC communication interface
func (th TelegramHandler) SendMessage(ctx context.Context, msg *pb.Message) (*pb.Reply, error) {
	// echo received messages into announcement channel
	th.tg_ann_ch <- msg.Text
	// log.Printf("Received message: %v", msg.Text)
	// send back acknowledge
	return &pb.Reply{Text: "ack"}, nil
}

func (th TelegramHandler) startPythonListeners() {

	// start gRPC server
	lis, err := net.Listen("tcp", ":"+th.cred.Grpc_port)
	if err != nil {
		th.log.Fatal("failed to listen to gRPC")
	}
	server := grpc.NewServer()
	// register message receiver object (service function should be implemented based on .proto file :: SendMessage())
	pb.RegisterMessengerServer(server, &th)

	th.log.Info("gRPC listening on", zap.String("port", th.cred.Grpc_port))

	// listening in separate goroutine
	go func() {
		//defer server.GracefulStop()
		if err := server.Serve(lis); err != nil {
			th.log.Fatal("gRPC server stopped")
		}
	}()

	// start telethon python listener
	cmd_telegram_listener_telethon := exec.Command("python3", "./python/telegram_listener_telethon.py")
	err = cmd_telegram_listener_telethon.Start()
	if err != nil {
		fmt.Printf("Error starting command: %v", err)
		return
	}

	go func() {
		defer func() {
			if err := cmd_telegram_listener_telethon.Process.Kill(); err != nil {
				fmt.Printf("Error killing command: %v\n", err)
			}
		}()
		err = cmd_telegram_listener_telethon.Wait()
		if err != nil {
			fmt.Printf("Error running command: %v", err)
			return
		}
	}()

	// start pyrogram python listener
	cmd_telegram_listener_pyrogram := exec.Command("python3", "./python/telegram_listener_pyrogram.py")
	err = cmd_telegram_listener_pyrogram.Start()
	if err != nil {
		fmt.Printf("Error starting command: %v", err)
		return
	}
	go func() {
		defer func() {
			if err := cmd_telegram_listener_pyrogram.Process.Kill(); err != nil {
				fmt.Printf("Error killing command: %v\n", err)
			}
		}()
		err = cmd_telegram_listener_pyrogram.Wait()
		if err != nil {
			fmt.Printf("Error running command: %v", err)
			return
		}
	}()
}

func (th TelegramHandler) pythonListenerTelethon() {
	cmd := exec.Command("python3", "./python/telegram_listener_telethon.py")
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		th.log.Fatal(err.Error())
	}

	cmd.Start()
	buf := bufio.NewReader(stdout)

	for {
		line, _, _ := buf.ReadLine()
		th.tg_ann_ch <- "[TELETHON cmd] " + string(line)
		time.Sleep(100 * time.Millisecond)
	}
}

func (th TelegramHandler) pythonListenerPyrogram() {
	cmd := exec.Command("python3", "./python/telegram_listener_pyrogram.py")
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		th.log.Fatal(err.Error())
	}

	cmd.Start()
	buf := bufio.NewReader(stdout)

	for {
		line, _, _ := buf.ReadLine()
		th.tg_ann_ch <- "[PYROGRAM] " + string(line)
		time.Sleep(100 * time.Millisecond)
	}
}

func (th TelegramHandler) newChannelMessage(ctx context.Context, e tg.Entities, update *tg.UpdateNewChannelMessage) error {
	m, ok := update.Message.(*tg.Message)
	if !ok {
		//th.log.Error("newChannelMessage")
		return nil
	}
	// channel id
	channelID := update.Message.(*tg.Message).PeerID.(*tg.PeerChannel).GetChannelID()
	// get channel name
	channelName, ok := e.Channels[channelID].GetUsername()
	if !ok {
		th.log.Error("channel name not set")
	}
	// channel filter
	if channelName != th.cred.Tg_announcement_channel_name &&
		"https://t.me/"+channelName != th.cred.Tg_announcement_channel_name {
		th.log.Info("tg msg filtered",
			zap.Int64("channelID", channelID),
			zap.String("channelName", channelName),
			zap.String("GetTitle()", e.Channels[channelID].GetTitle()))
		return nil
	}

	th.tg_ann_ch <- m.GetMessage()
	th.log.Info("tg channel msg rx",
		zap.Int64("channelID", channelID),
		zap.String("channelName", channelName),
		zap.String("GetTitle()", e.Channels[channelID].GetTitle()),
		zap.Any("tg_ann_ch", m.GetMessage()))

	return nil
}

func (th TelegramHandler) Run(ctx context.Context) error {
	dispatcher := tg.NewUpdateDispatcher()
	client := th.client(ctx, dispatcher)

	dispatcher.OnNewChannelMessage(th.newChannelMessage)
	dispatcher.OnNewMessage(th.newMessage)

	return client.Run(ctx, func(ctx context.Context) error {
		// check authentication
		err := th.auth(ctx, client)
		if err != nil {
			th.log.Error("authentication failed")
			return err
		} else {
			th.log.Info("authentication passed")
		}

		// setup reply
		sender := message.NewSender(client.API())
		my_bot_channel := sender.Resolve(th.cred.Tg_bot_channel_name)

		// process messages to be sent
		for msg_2_bot_ch := range th.tg_bot_ch {
			th.log.Info(msg_2_bot_ch)

			if _, err := my_bot_channel.Text(ctx, "[go] "+msg_2_bot_ch); err != nil {
				return err
			}
		}

		<-ctx.Done()
		return ctx.Err()
	})
}

// client creates new *telegram.Client
func (th *TelegramHandler) client(ctx context.Context, handler telegram.UpdateHandler) *telegram.Client {
	// return with new telegram client
	return telegram.NewClient(th.cred.Tg_api_id, th.cred.Tg_api_hash,
		telegram.Options{
			Logger:        th.log,
			UpdateHandler: handler,
			SessionStorage: &session.FileStorage{
				Path: "./session.json",
			},
		})
}

// authentication
func (th *TelegramHandler) auth(ctx context.Context, client *telegram.Client) error {
	_, err := client.Self(ctx)
	if auth.IsUnauthorized(err) {
		// authentication needed
		codePrompt := func(ctx context.Context, sentCode *tg.AuthSentCode) (string, error) {
			// prompt password
			fmt.Print("Enter code: ")
			code, err := bufio.NewReader(os.Stdin).ReadString('\n')
			if err != nil {
				return "", err
			}
			return strings.TrimSpace(code), nil
		}
		// setup and perform authentication flow
		if err := auth.NewFlow(
			auth.Constant(th.cred.Telephone, "-", auth.CodeAuthenticatorFunc(codePrompt)),
			auth.SendCodeOptions{},
		).Run(ctx, client.Auth()); err != nil {
			panic(err)
		}
	}
	_, err = client.Self(ctx)
	return err
}
