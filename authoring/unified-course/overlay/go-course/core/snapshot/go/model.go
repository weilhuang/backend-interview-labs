// Package ownership 演示订单快照的数据所有权；这是有限数据结构的教学模型。
package ownership

// Line 表示一条订单明细。Tags 是可变切片，所以复制 Line 值并不复制标签元素。
type Line struct {
	SKU      string   `json:"sku"`
	Quantity int      `json:"quantity"`
	Tags     []string `json:"tags"`
}

// Order 不包含指针、时间、环或接口；不把本实验推广成任意对象深复制器。
type Order struct {
	ID       string            `json:"id"`
	Lines    []Line            `json:"lines"`
	Metadata map[string]string `json:"metadata"`
}
