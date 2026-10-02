package main

import ("fmt"; "io"; "os"; lab "academy.example/go-order-total")

func run(w io.Writer) error {
 order:=lab.Order{Lines:[]lab.Line{{UnitCents:199,Quantity:2},{UnitCents:50,Quantity:3}}}
 total,err:=order.TotalCents();if err!=nil{return err}
 _,err=fmt.Fprintf(w,"订单总额=%d分\n原数量=%d\n",total,order.Lines[0].Quantity)
 return err
}

func main(){if err:=run(os.Stdout);err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}}
