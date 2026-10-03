package lab

import ("testing"

)

func TestContract(t *testing.T) {
 cases := []struct{name, input, want string}{
  {"中文", "小林", "你好，小林！"}, {"空串", "", "你好，访客！"},
  {"空白", " \t\n", "你好，访客！"}, {"英文", "Ada", "你好，Ada！"},
  {"保留内部空格", "李 小林", "你好，李 小林！"}, {"去除边缘空白", "\u3000小林 ", "你好，小林！"},
  {"标点", "A-B", "你好，A-B！"}, {"重复调用", "第二次", "你好，第二次！"},
 }
 for _, c := range cases { t.Run(c.name, func(t *testing.T) { if got:=Greeting(c.input);got!=c.want {t.Fatalf("GREETING: 输入%q，得到%q，期望%q",c.input,got,c.want)} }) }
}
