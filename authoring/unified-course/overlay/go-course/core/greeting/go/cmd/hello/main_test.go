package main
import ("testing";"bytes";"errors")
type failingWriter struct{}
var errWrite=errors.New("模拟输出设备失败")
func (failingWriter) Write(p []byte)(int,error){return 0,errWrite}
func TestDemoOutput(t *testing.T){var out bytes.Buffer;if err:=run(&out);err!=nil{t.Fatal(err)};want:="你好，小林！\n你好，访客！\n你好，Ada！\n";if out.String()!=want{t.Fatalf("CALLER: 得到%q，期望%q",out.String(),want)}}
func TestOutputFailure(t *testing.T){if err:=run(failingWriter{});!errors.Is(err,errWrite){t.Fatalf("OUTPUT_ERROR: 必须传播输出失败，得到%v",err)}}
