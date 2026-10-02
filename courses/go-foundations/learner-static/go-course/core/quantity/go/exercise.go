package lab

import (
 "strings"
 "strconv"
 "errors"
)

// 错误哨兵：调用方用errors.Is辨认类别，不比较易变化的文案。
var ErrInvalidQuantity = errors.New("数量格式错误")
var ErrQuantityRange = errors.New("数量必须在1到1000之间")
const MaxQuantity = 1000
var _ = strings.TrimSpace
var _ = strconv.Atoi

func ParseQuantity(raw string) (int, error) {
	// 练习区开始：只替换下方函数体片段 🧪
	return 0, nil
	// 练习区结束
}
