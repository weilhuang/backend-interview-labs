package main
import("testing";"os";"os/exec";"bytes";"strings")
// 在本测试程序的独立子进程中执行真实main；关闭stdout使写入失败，验证退出码。
func TestMainProcess(t *testing.T) {
 if mode:=os.Getenv("ACADEMY_TEST_MAIN_CHILD");mode!="" {
  if mode=="output-failure" { if err:=os.Stdout.Close();err!=nil{os.Exit(99)} }
  main();os.Exit(0)
 }
 executable,err:=os.Executable();if err!=nil{t.Fatal(err)}
 for _,mode:=range []string{"normal","output-failure"} {t.Run(mode,func(t *testing.T){
  child:=exec.Command(executable,"-test.run=^TestMainProcess$")
  for _,e:=range os.Environ(){if !strings.HasPrefix(e,"ACADEMY_TEST_MAIN_CHILD=")&&!strings.HasPrefix(e,"GORACE="){child.Env=append(child.Env,e)}}
  child.Env=append(child.Env,"ACADEMY_TEST_MAIN_CHILD="+mode,"GORACE=atexit_sleep_ms=0")
  var out,stderr bytes.Buffer;child.Stdout=&out;child.Stderr=&stderr
  err:=child.Run()
  if mode=="normal" {if err!=nil||out.String()!="你好，小林！\n你好，访客！\n你好，Ada！\n"||stderr.Len()!=0{t.Fatalf("MAIN_CALL: err=%v stdout=%q stderr=%q",err,out.String(),stderr.String())};return}
  exit,ok:=err.(*exec.ExitError);if !ok||exit.ExitCode()!=1||stderr.Len()==0 {t.Fatalf("MAIN_EXIT: 输出失败必须stderr报告并exit1，err=%v stderr=%q",err,stderr.String())}
 })}
}
