// 本调用方始终调用学生实现；不会暗中切换到参考解。
package main

import (
	ownership "academy.example/go-ownership"
	"encoding/json"
	"fmt"
	"io"
	"os"
)

func run(out io.Writer) error {
	encoder := json.NewEncoder(out)
	encoder.SetIndent("", "  ")
	return encoder.Encode(ownership.Demo())
}

func main() {
	if err := run(os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "输出演示失败:", err)
		os.Exit(1)
	}
}
