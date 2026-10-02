package ownership

// DemoResult 是完整调用方的输出；快照应保留创建瞬间的数据。
type DemoResult struct {
	Live     []Order `json:"live"`
	Snapshot []Order `json:"snapshot"`
}

// Demo 先生成发货快照，再修改购物车，模拟两个业务环节相互独立。
func Demo() DemoResult {
	live := []Order{{ID: "订单-001", Lines: []Line{{SKU: "书", Quantity: 1, Tags: []string{"原价"}}}, Metadata: map[string]string{"status": "待付款"}}}
	snapshot := SnapshotOrders(live)
	live[0].Lines[0].Quantity = 2
	live[0].Lines[0].Tags[0] = "活动价"
	live[0].Metadata["status"] = "已付款"
	return DemoResult{Live: live, Snapshot: snapshot}
}
