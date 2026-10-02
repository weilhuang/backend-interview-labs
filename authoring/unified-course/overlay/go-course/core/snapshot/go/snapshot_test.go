package ownership_test

import (
	ownership "academy.example/go-ownership"
	"reflect"
	"testing"
)

func fixture() []ownership.Order {
	return []ownership.Order{
		{ID: "订单-A", Lines: []ownership.Line{{SKU: "书", Quantity: 2, Tags: []string{"原价", "现货"}}}, Metadata: map[string]string{"status": "待付款", "channel": "门店"}},
		{ID: "订单-B", Lines: []ownership.Line{{SKU: "笔", Quantity: 3, Tags: []string{"蓝色"}}}, Metadata: map[string]string{"status": "已付款"}},
	}
}

// 每次从新输入开始，先核对公开值契约，避免错误形状引发panic掩盖真实断言。
func pair(t *testing.T) ([]ownership.Order, []ownership.Order) {
	t.Helper()
	src := fixture()
	dst := ownership.SnapshotOrders(src)
	if !reflect.DeepEqual(src, dst) {
		t.Fatalf("C1 复制瞬间应保留全部值与顺序：输入=%#v，快照=%#v", src, dst)
	}
	return src, dst
}

func TestSnapshotContract(t *testing.T) {
	cases := []struct {
		name  string
		check func(*testing.T)
	}{
		{"CP1_NilInput", func(t *testing.T) {
			if got := ownership.SnapshotOrders(nil); got != nil {
				t.Fatalf("C2 nil输入必须返回nil，得到%#v", got)
			}
		}},
		{"CP1_NonNilEmpty", func(t *testing.T) {
			got := ownership.SnapshotOrders([]ownership.Order{})
			if got == nil || len(got) != 0 {
				t.Fatalf("C2 非nil空输入必须仍为非nil空切片，得到%#v", got)
			}
		}},
		{"CP1_ValueAndOrder", func(t *testing.T) { pair(t) }},
		{"CP1_TopOutputToInput", func(t *testing.T) {
			src, dst := pair(t)
			dst[0].ID = "快照被修改"
			if src[0].ID != "订单-A" {
				t.Fatal("C3 修改快照Order值污染了输入顶层数组")
			}
		}},
		{"CP1_TopInputToOutput", func(t *testing.T) {
			src, dst := pair(t)
			src[0].ID = "输入被修改"
			if dst[0].ID != "订单-A" {
				t.Fatal("C3 修改输入Order值污染了快照")
			}
		}},
		{"CP2_LineOutputToInput", func(t *testing.T) {
			src, dst := pair(t)
			dst[0].Lines[0].Quantity = 99
			if src[0].Lines[0].Quantity != 2 {
				t.Fatal("C3 明细切片仍共享底层数组：快照修改影响输入")
			}
		}},
		{"CP2_LineInputToOutput", func(t *testing.T) {
			src, dst := pair(t)
			src[0].Lines[0].SKU = "橡皮"
			if dst[0].Lines[0].SKU != "书" {
				t.Fatal("C3 明细切片仍共享底层数组：输入修改影响快照")
			}
		}},
		{"CP2_TagOutputToInput", func(t *testing.T) {
			src, dst := pair(t)
			dst[0].Lines[0].Tags[0] = "促销"
			if src[0].Lines[0].Tags[0] != "原价" {
				t.Fatal("C3 复制Line后还须复制Tags，否则标签互相污染")
			}
		}},
		{"CP2_TagInputToOutput", func(t *testing.T) {
			src, dst := pair(t)
			src[0].Lines[0].Tags[1] = "缺货"
			if dst[0].Lines[0].Tags[1] != "现货" {
				t.Fatal("C3 输入标签变化污染了快照")
			}
		}},
		{"CP2_MapOutputToInput", func(t *testing.T) {
			src, dst := pair(t)
			dst[0].Metadata["status"] = "取消"
			delete(dst[0].Metadata, "channel")
			dst[0].Metadata["new"] = "值"
			if !reflect.DeepEqual(src[0].Metadata, fixture()[0].Metadata) {
				t.Fatal("C3 map的更新/删除/新增污染了输入")
			}
		}},
		{"CP2_MapInputToOutput", func(t *testing.T) {
			src, dst := pair(t)
			src[0].Metadata["status"] = "取消"
			delete(src[0].Metadata, "channel")
			if !reflect.DeepEqual(dst[0].Metadata, fixture()[0].Metadata) {
				t.Fatal("C3 输入map变化污染了快照")
			}
		}},
		{"CP2_NilNested", func(t *testing.T) {
			src := []ownership.Order{{ID: "空订单"}, {Lines: []ownership.Line{{SKU: "无标签"}}}}
			if got := ownership.SnapshotOrders(src); !reflect.DeepEqual(got, src) {
				t.Fatalf("C2 嵌套nil状态必须保留：%#v", got)
			}
		}},
		{"CP2_EmptyNested", func(t *testing.T) {
			src := []ownership.Order{{Lines: []ownership.Line{}, Metadata: map[string]string{}}, {Lines: []ownership.Line{{Tags: []string{}}}}}
			if got := ownership.SnapshotOrders(src); !reflect.DeepEqual(got, src) {
				t.Fatalf("C2 嵌套非nil空容器必须保留：%#v", got)
			}
		}},
		{"CP3_SharedInputContainersSeparate", func(t *testing.T) {
			line := []ownership.Line{{SKU: "共享输入", Tags: []string{"原标签"}}}
			meta := map[string]string{"owner": "原值"}
			src := []ownership.Order{{Lines: line, Metadata: meta}, {Lines: line, Metadata: meta}}
			dst := ownership.SnapshotOrders(src)
			if !reflect.DeepEqual(src, dst) {
				t.Fatal("C1 共享输入仍需保持初始值")
			}
			dst[0].Lines[0].Tags[0] = "新标签"
			dst[0].Metadata["owner"] = "新值"
			if dst[1].Lines[0].Tags[0] != "原标签" || dst[1].Metadata["owner"] != "原值" {
				t.Fatal("C4 输出各订单应独立，不能保留输入共享容器的别名")
			}
			if src[0].Lines[0].Tags[0] != "原标签" || src[0].Metadata["owner"] != "原值" {
				t.Fatal("C3 修改输出污染了共享输入")
			}
		}},
		{"CP3_RepeatedCallsSeparate", func(t *testing.T) {
			src := fixture()
			a := ownership.SnapshotOrders(src)
			b := ownership.SnapshotOrders(src)
			if !reflect.DeepEqual(a, src) || !reflect.DeepEqual(b, src) {
				t.Fatal("C1 连续调用仍需保留值")
			}
			a[0].Lines[0].Tags[0] = "第一次快照修改"
			a[0].Metadata["status"] = "取消"
			if !reflect.DeepEqual(b, fixture()) {
				t.Fatal("C4 两次快照不应共享可变存储")
			}
		}},
		{"CP3_NoMutationDuringCall", func(t *testing.T) {
			src := fixture()
			ownership.SnapshotOrders(src)
			if !reflect.DeepEqual(src, fixture()) {
				t.Fatal("C5 SnapshotOrders调用本身不得改写或排序输入")
			}
		}},
		{"CP3_SpareCapacityAppend", func(t *testing.T) {
			backing := []ownership.Order{{ID: "可见"}, {ID: "尾部哨兵"}}
			tags := []string{"标签", "标签哨兵"}
			lines := []ownership.Line{{SKU: "可见明细", Tags: tags[:1]}, {SKU: "明细哨兵"}}
			backing[0].Lines = lines[:1]
			src := backing[:1]
			dst := ownership.SnapshotOrders(src)
			if !reflect.DeepEqual(src, dst) {
				t.Fatal("C1 容量超过长度时也只保留可见值")
			}
			dst[0].Lines[0].Tags = append(dst[0].Lines[0].Tags, "覆盖标签")
			dst[0].Lines = append(dst[0].Lines, ownership.Line{SKU: "覆盖明细"})
			dst = append(dst, ownership.Order{ID: "覆盖订单"})
			if tags[1] != "标签哨兵" || lines[1].SKU != "明细哨兵" || backing[1].ID != "尾部哨兵" {
				t.Fatal("C3 append复用了输入的剩余容量，污染了不可见尾部")
			}
		}},
		{"CP3_StringsExact", func(t *testing.T) {
			src := []ownership.Order{{ID: "\x00中\n", Lines: []ownership.Line{{SKU: " \xff ", Tags: []string{"", "\t"}}}, Metadata: map[string]string{"": "\x00", "\n": "✓"}}}
			if got := ownership.SnapshotOrders(src); !reflect.DeepEqual(got, src) {
				t.Fatal("C6 快照不负责清洗、校验、编码或归一化原值")
			}
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, tc.check)
	}
}

// Fuzz执行有界结构上的性质；默认go test只运行三个种子，额外fuzz必须单独报告。
func FuzzSnapshotIsolation(f *testing.F) {
	f.Add([]byte("原价"))
	f.Add([]byte{})
	f.Add([]byte{0, 255, 10})
	f.Fuzz(func(t *testing.T, data []byte) {
		if len(data) > 256 {
			t.Skip("将单个fuzz输入限制为256字节")
		}
		value := string(data)
		src := []ownership.Order{{ID: value, Lines: []ownership.Line{{SKU: value, Tags: []string{value}}}, Metadata: map[string]string{value: value}}}
		dst := ownership.SnapshotOrders(src)
		if !reflect.DeepEqual(src, dst) {
			t.Fatal("C1 fuzz初始值不一致")
		}
		dst[0].Lines[0].Tags[0] = value + "changed"
		dst[0].Metadata[value] = value + "changed"
		if src[0].Lines[0].Tags[0] != value || src[0].Metadata[value] != value {
			t.Fatal("C3 fuzz修改快照污染输入")
		}
	})
}
