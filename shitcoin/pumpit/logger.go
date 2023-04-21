package main

import (
	"os"
	"path/filepath"
	"sync"
	"time"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

var datetime string
var once_logger sync.Once

func genFileName(file_name_extension string) string {
	once_logger.Do(func() {
		datetime = time.Now().Format("20060102_150405")
	})
	if len(file_name_extension) > 0 {
		file_name_extension = "_" + file_name_extension
	}
	file_name := datetime + "_pumpit" + file_name_extension + ".log"
	log_path := filepath.Join(".", "logs")
	log_file := filepath.Join(log_path, file_name)
	if _, err := os.Stat(log_file); os.IsNotExist(err) {
		os.MkdirAll(log_path, os.ModePerm)
	}
	return log_file
}

func ConsoleFileLogger() *zap.Logger {
	config := zap.NewProductionEncoderConfig()
	fileEncoder := zapcore.NewJSONEncoder(config)
	config.EncodeTime = zapcore.ISO8601TimeEncoder
	consoleEncoder := zapcore.NewConsoleEncoder(config)

	fname := genFileName("")
	logFile, _ := os.OpenFile(fname, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	writer := zapcore.AddSync(logFile)
	level := zap.InfoLevel
	core := zapcore.NewTee(
		zapcore.NewCore(fileEncoder, writer, level),
		zapcore.NewCore(consoleEncoder, zapcore.AddSync(os.Stdout), level),
	)
	return zap.New(core, zap.AddCaller(), zap.AddStacktrace(zapcore.ErrorLevel))
}

func MinimalFileLogger(file_name_ext string) *zap.Logger {
	config := zap.NewProductionEncoderConfig()
	config.LevelKey = zapcore.OmitKey
	config.CallerKey = zapcore.OmitKey
	fileEncoder := zapcore.NewJSONEncoder(config)

	fname := genFileName(file_name_ext)
	logFile, _ := os.OpenFile(fname, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	writer := zapcore.AddSync(logFile)
	level := zap.InfoLevel
	core := zapcore.NewTee(
		zapcore.NewCore(fileEncoder, writer, level),
	)
	return zap.New(core, zap.AddCaller(), zap.AddStacktrace(zapcore.ErrorLevel))
}
