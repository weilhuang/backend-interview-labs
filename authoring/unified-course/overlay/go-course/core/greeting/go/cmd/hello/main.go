package main

import ("fmt"; "io"; "os"; lab "academy.example/go-greeting")

func run(w io.Writer) error {
 for _, name := range []string{"小林", " ", "Ada"} { if _,err:=fmt.Fprintln(w, lab.Greeting(name));err!=nil{return err} }
 return nil
}

func main(){if err:=run(os.Stdout);err!=nil{fmt.Fprintln(os.Stderr,err);os.Exit(1)}}
