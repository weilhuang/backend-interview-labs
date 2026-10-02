package main

import ("fmt"; "io"; "os"; lab "academy.example/go-quantity")

func run(w io.Writer) error {
 for _,raw:=range []string{" 12 ", "abc", "1001"} {
  n,err:=lab.ParseQuantity(raw)
  if err!=nil {if _,e:=fmt.Fprintf(w,"输入%q：%v\n",raw,err);e!=nil{return e};continue}
  if _,e:=fmt.Fprintf(w,"输入%q：数量=%d\n",raw,n);e!=nil{return e}
 }
 return nil
}

func main(){if err:=run(os.Stdout);err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}}
