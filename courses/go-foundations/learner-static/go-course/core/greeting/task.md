# C13-01 第一次Go构建测试和调试

> 源码候选：Go/JUnit运行、主课程接入与原生IDE体验尚待验证；以下输出是练习合同的预期，不是已执行的结果。

## 本题可验收合同
去掉名字首尾Unicode空白；全空白或空串视为“访客”；保留内部空格与原有大小写；输出“你好，名字！”（中文逗号和感叹号）。不读环境变量、不读文件，不记住上一次调用。


## 你正在使用什么
这是主Java Academy课程里的可见Go源码练习，由公开JUnit桥调用真实go test；不是原生Go Academy课程。IDE的Go插件、Go断点与调试器尚未验证，不以“点了Check”推断所有测试执行。没有Docker，也不需要外部Go库。

- module（模块）：go.mod声明这一组代码的导入根和语言版本；类似Java项目坐标边界，但不是Maven的完整等价物
- package（包）：同目录Go文件的组织单位，本题根包叫lab；import引用其导入路径
- package main + func main：可执行程序入口，位于cmd子目录；main调用你补的函数
- *_test.go：测试源码，go test编译测试入口并运行Test开头的函数；go run不运行测试
- 零值：未赋值变量自带默认值；int为0、string为空串、error为nil。零值可用不代表符合业务合同

## 0. 先确认工具和目录
仓库不携带Go SDK。请按项目统一工具链要求准备官方Go 1.27.1；将GO_EXECUTABLE设为该编译器可执行文件的完整路径。下列是已设置该变量后的POSIX终端命令；不要把示例变量当安装脚本。

```sh
"$GO_EXECUTABLE" version
export GOTOOLCHAIN=local GOWORK=off GOENV=off GOFLAGS= GOPROXY=off GOSUMDB=off
```
预期第一行类似 go version go1.27.1 linux/amd64；系统平台可以不同，版本必须精确匹配。变量为空、路径不存在或版本不同是INVALID_ENV，不是题做错。Java桥也检查版本，且不会悄悄下载工具链。
在本题目录进入go子目录再运行下面命令；看到go.mod才说明目录正确。GO_EXECUTABLE与公共桥同名，Java入口不默认猜系统go路径。

## 1. 先读完整调用链，不要立即复制答案
```text
cmd/子命令/main.go -> lab.练习函数 -> 返回值/错误 -> 终端输出
                               ^
             contract_test.go逐项断言
Java Academy Check -> test/GoContractTest.java -> src/GoTestBridge.java
                                                -> go test -count=1 -v ./...
```
打开cmd里的main.go，找run如何调用练习函数；打开contract_test.go，读一组输入和期望。再看源码中“练习区”标记。只替换两条标记之间的代码，不改函数签名、import或测试。两种标准答案都能仅填进这一块，helper方案使用函数内小函数，不需要额外扩大编辑区。

## 2. 确认红灯是业务红灯
先构建所有包：
```sh
"$GO_EXECUTABLE" build -buildvcs=false ./...
```
预期无输出、退出0。-buildvcs=false只关闭可选Git版本水印，让从压缩包或受限工作区学习不依赖上层仓库状态；它不跳过编译或测试。go build只证明能编译；go run构建并执行main；go test还运行断言，不能互相替代。

```sh
"$GO_EXECUTABLE" test -run '^$' ./...
"$GO_EXECUTABLE" test -count=1 -v ./...
```
第一条只编译，starter应成功；它故意没有执行业务测试，绝不能据此算通过。第二条starter应以GREETING/QUANTITY/TOTAL业务消息失败，表明接线完整。如果是syntax error或undefined，先修编译；若显示[no test files]或SKIP，不算完成。超时属于检查失败，不是“测试已覆盖”。

## 3. 一次只补一个行为
先处理最简单成功输入，运行某个子例；再补空输入/边界；最后运行全部测试。命令中的TestContract是本题固定的表驱动测试名：
```sh
"$GO_EXECUTABLE" test -count=1 -v -run TestContract ./...
"$GO_EXECUTABLE" test -count=1 -v ./...
"$GO_EXECUTABLE" vet ./...
```
预期业务子例、调用方TestDemoOutput、输出失败TestOutputFailure、真实main进程TestMainProcess都PASS。vet无输出且退出0表示静态检查通过，不替代业务测试。race检测需平台支持的C工具链：如环境不支持，记录NOT_RUN及原因，不把它写成通过。

## 4. 运行调用方并做迁移
```sh
"$GO_EXECUTABLE" run ./cmd/hello
```
正确实现预期：
```text
你好，小林！
你好，访客！
你好，Ada！
```
逐行把输出对应到main.go里的输入。若输出不一致，先直接对比函数返回值，再看调用方格式化。错误不一定是panic：有些错误通过第二返回值传给调用方处理。
修复后保留starter红灯记录与自己的绿灯记录，回答本文末尾的追问。观察题：画出参数、局部变量、返回值。Go断点操作要等IDE插件单独验收；本候选不能宣称已验证调试器，可用测试和打印先跟踪这三个值。此观察不伪装成自动评分通过。

## 5. 常见排错
- 找不到go.mod：在本题go目录运行，不能在课程根盲跑
- import未使用：不要删固定import；exercise.go中保留编译锚点让两种练习区实现共享import集合，生产代码通常只导入真正需要的包
- 刚改代码却读到旧绿灯：加-count=1；公共桥禁用Gradle缓存并核对具体子例名
- 测试文件改绿：不属于完成；测试与调用方是合同，修练习区
- 中文标点不同：字符串比较逐字节比较，中文逗号和英文逗号不相同
- 不知道如何恢复：完整答案在go/answers/*.go.txt；打开[作者源中的starter占位定义](../../../../overlay/go-course/core/greeting/task-info.yaml)，把go/exercise.go练习区替换为其中placeholder_text的内容，勿覆盖其他文件。学员预览目录不包含task-info.yaml，请使用此链接

## 分步练习与迁移观察：第一次写Go
1. 看exercise.go的package lab，再看cmd/hello/main.go的package main。前者装可复用函数，后者是可启动程序。先读main最后一行如何处理输出错误，再读run中for循环。`[]string{...}`是字符串切片字面量，先理解为按顺序存放三个名字的小列表。
2. 在练习区先写`return "你好，" + name + "！"`。跑`"$GO_EXECUTABLE" test -v -run 'TestContract/中文'`应PASS，再跑空串子例应FAIL。这是故意分步暴露问题，不能停在第一个绿灯。
3. 写`name = strings.TrimSpace(name)`后再判`name == ""`，空串时返回访客，其余拼接。先问自己：参数name是字符串值还是整个用户对象？返回值在哪一层打印？最后跑全套，手动对照三行输出。
4. 不必熟悉调试器也能先跟踪：临时在练习区增加打印会污染main输出，不建议这样做；优先在测试断言消息里观察输入/输出。真正IDE断点练习留在原生验证后：在Greeting入口停下，观察name，单步经过TrimSpace，观察return，回到run。此步骤目前NOT_RUN。

## 本题逐步实现
先规范化字符串，再判空，最后拼接返回值。strings.TrimSpace返回新字符串，name重新赋值只改变本次函数的局部变量。

## Java对照
Java 的 static String greeting(String name) 对应 Go 的包级函数。Go 不需要为了一个函数创建类；string 零值是空串，不能是 Java 的 null。Go 的 := 声明并推断类型，= 给已有变量赋值。

## 提示H1–H4
- H1：先把合同中的正常输入手算一遍，再读TestContract同名子例
- H2：先规范化字符串，再判空，最后拼接返回值
- H3：阅读answers中第一种完整答案，标出每一个提前return对应的合同
- H4：逐行替换练习区，再对照第二种实现；不用修改import和测试也应全部通过

## 标准答案与解释

### explicit
仅填入练习区：
```go
	name = strings.TrimSpace(name)
	if name == "" { return "你好，访客！" }
	return "你好，" + name + "！"
```
完整可比较源码见go/answers/explicit.go.txt。

### helpers
仅填入练习区：
```go
	normalize := func(s string) string {
		s = strings.TrimSpace(s)
		if s == "" { return "访客" }
		return s
	}
	return "你好，" + normalize(name) + "！"
```
完整可比较源码见go/answers/helpers.go.txt。

两种实现遵守同一合同，而不是两个不同预期。先规范化字符串，再判空，最后拼接返回值。strings.TrimSpace返回新字符串，name重新赋值只改变本次函数的局部变量。

## 面试递进与迁移
1. 为什么不能把 strings.TrimSpace(name) 写一行却丢弃返回值？因为字符串操作不原地修改。
2. package 与 module 有什么区别？前者组织同目录的源码，后者由go.mod定义依赖及导入路径边界。
3. main、Greeting、TestContract分别由谁调用？操作系统启动main；main调用Greeting；go test生成测试入口调用TestContract。
4. 迁移：如果欢迎语要支持不同语言，该把语言作为参数还是读全局环境？说明可重复测试与依赖显式化的取舍。

## 图示
![调用与返回](go/diagrams/flow.png)

## 验收边界
原矩阵用例数量是设计估算，不当已通过数。本候选每题一个Academy task，教学阶段不冒充三个已交互验收task。原生IDE导入、Check及Go调试仍NOT_RUN；Go/Java命令执行结果需要单独记录。
