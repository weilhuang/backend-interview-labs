package lab

import (
 "strings"
)

var _ = strings.TrimSpace

func Greeting(name string) string {
	// 练习区开始：只替换下方函数体片段 🧪
	name = strings.TrimSpace(name)
	if name == "" { return "你好，访客！" }
	return "你好，" + name + "！"
	// 练习区结束
}
