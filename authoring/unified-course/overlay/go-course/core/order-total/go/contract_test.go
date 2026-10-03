package lab

import ("testing"
"errors"
 "math"
 "reflect"
)

func TestContract(t *testing.T) {
 cases:=[]struct{name string; lines []Line; want int64; err error}{
 {"零值",nil,0,nil},{"空非nil",[]Line{},0,nil},{"一行",[]Line{{199,2}},398,nil},
 {"多行",[]Line{{199,2},{50,3}},548,nil},{"免费商品",[]Line{{0,math.MaxInt64}},0,nil},
 {"负单价",[]Line{{-1,2}},0,ErrInvalidLine},{"零数量",[]Line{{1,0}},0,ErrInvalidLine},
 {"负数量",[]Line{{1,-1}},0,ErrInvalidLine},{"精确大整数",[]Line{{9007199254740993,1}},9007199254740993,nil},
 {"最大值",[]Line{{math.MaxInt64,1}},math.MaxInt64,nil},{"乘法溢出",[]Line{{math.MaxInt64,2}},0,ErrTotalOverflow},
 {"加法溢出",[]Line{{math.MaxInt64,1},{1,1}},0,ErrTotalOverflow},
 {"刚好边界",[]Line{{math.MaxInt64/2,2},{1,1}},math.MaxInt64,nil},
 {"乘溢出先于后行非法",[]Line{{math.MaxInt64,2},{-1,1}},0,ErrTotalOverflow},
 {"加溢出先于后行非法",[]Line{{math.MaxInt64,1},{1,1},{-1,1}},0,ErrTotalOverflow},
 {"非法先于后行溢出",[]Line{{-1,1},{math.MaxInt64,2}},0,ErrInvalidLine},
 {"错误不返回部分和",[]Line{{10,1},{-1,1}},0,ErrInvalidLine},
 }
 for _,c:=range cases {t.Run(c.name,func(t *testing.T){got,err:=(Order{Lines:c.lines}).TotalCents();if got!=c.want||!errors.Is(err,c.err){t.Fatalf("TOTAL: 得到(%d,%v)，期望(%d,%v)",got,err,c.want,c.err)}})}
 t.Run("输入不改写",func(t *testing.T){lines:=[]Line{{7,2},{9,3}};before:=append([]Line(nil),lines...);_,_= (Order{lines}).TotalCents();if !reflect.DeepEqual(lines,before){t.Fatal("TOTAL_OWNERSHIP: 输入被改写")}})
 t.Run("共享切片不改写",func(t *testing.T){lines:=[]Line{{7,2}};a,b:=Order{lines},Order{lines};_,_=a.TotalCents();if b.Lines[0].Quantity!=2{t.Fatal("TOTAL_ALIAS: 值接收者仍共享切片底层数组")}})
 t.Run("重复调用",func(t *testing.T){o:=Order{[]Line{{7,2}}};for i:=0;i<3;i++{if n,e:=o.TotalCents();n!=14||e!=nil{t.Fatalf("TOTAL_REPEAT: %d %v",n,e)}}})
 t.Run("指针也能调用",func(t *testing.T){o:=&Order{[]Line{{7,2}}};if n,e:=o.TotalCents();n!=14||e!=nil{t.Fatalf("TOTAL_POINTER: %d %v",n,e)}})
}
func TestFailureRecovery(t *testing.T) {
 bad:=Order{[]Line{{math.MaxInt64,2}}};if n,e:=bad.TotalCents();n!=0||!errors.Is(e,ErrTotalOverflow){t.Fatalf("TOTAL_FAILURE: %d %v",n,e)}
 good:=Order{[]Line{{5,3}}};if n,e:=good.TotalCents();n!=15||e!=nil{t.Fatalf("TOTAL_RECOVERY: %d %v",n,e)}
}
