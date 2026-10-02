package lab

import ("testing"
"errors"
)

func TestContract(t *testing.T) {
 cases:=[]struct{name,raw string; want int; err error}{
 {"最小值","1",1,nil},{"普通值","12",12,nil},{"上限","1000",1000,nil},{"前导零","00012",12,nil},
 {"边缘空白"," \t12\u3000",12,nil},{"空串","",0,ErrInvalidQuantity},{"空白"," \n",0,ErrInvalidQuantity},
 {"字母","12x",0,ErrInvalidQuantity},{"小数","1.5",0,ErrInvalidQuantity},{"正号","+1",0,ErrInvalidQuantity},
 {"负数","-1",0,ErrInvalidQuantity},{"零","0",0,ErrQuantityRange},{"超上限","1001",0,ErrQuantityRange},
 {"溢出","9999999999999999999999999999999999999999999999",0,ErrQuantityRange},
 {"内部空格","1 2",0,ErrInvalidQuantity},{"非ASCII数字","１２",0,ErrInvalidQuantity},
 }
 for _,c:=range cases {t.Run(c.name,func(t *testing.T){got,err:=ParseQuantity(c.raw);if got!=c.want||!errors.Is(err,c.err){t.Fatalf("QUANTITY: %q 得到(%d,%v)，期望(%d,%v)",c.raw,got,err,c.want,c.err)}})}
}
func TestFailureRecovery(t *testing.T) {
 for _,raw:=range []string{"100000000000000000000000000x", "1\x002", "12\n3"} {if _,e:=ParseQuantity(raw);!errors.Is(e,ErrInvalidQuantity){t.Fatalf("QUANTITY_SYNTAX: %q错误分类: %v",raw,e)}}
 if n,e:=ParseQuantity("2");n!=2||e!=nil {t.Fatalf("QUANTITY_RECOVERY: 坏输入后不能污染下一次调用: %d %v",n,e)}
}
