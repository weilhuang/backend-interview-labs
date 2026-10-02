package main
import ("testing";"bytes";"errors")
type failingWriter struct{}
var errWrite=errors.New("模拟输出设备失败")
func (failingWriter) Write(p []byte)(int,error){return 0,errWrite}
func TestDemoOutput(t *testing.T){var out bytes.Buffer;if err:=run(&out);err!=nil{t.Fatal(err)};want:="输入\" 12 \"：数量=12\n输入\"abc\"：数量格式错误\n输入\"1001\"：数量必须在1到1000之间\n";if out.String()!=want{t.Fatalf("CALLER: 得到%q，期望%q",out.String(),want)}}
func TestOutputFailure(t *testing.T){if err:=run(failingWriter{});!errors.Is(err,errWrite){t.Fatalf("OUTPUT_ERROR: 必须传播输出失败，得到%v",err)}}
