# C13-02 变量控制流与可靠输入

> 源码候选：Go/JUnit运行、主课程接入与原生IDE体验尚待验证；以下输出是练习合同的预期，不是已执行的结果。

## 本题可验收合同
先TrimSpace去掉首尾Unicode空白；剩余必须是一个或多个ASCII数字0至9，可有前导零，不接受+、-、小数、全角数字、内部空白或NUL。语法不合法返回(0, ErrInvalidQuantity)；合法数字但不在1..1000（含超出int容量）返回(0, ErrQuantityRange)。语法错误优先于范围错误。成功返回(n,nil)。


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
"$GO_EXECUTABLE" run ./cmd/quantity
```
正确实现预期：
```text
输入" 12 "：数量=12
输入"abc"：数量格式错误
输入"1001"：数量必须在1到1000之间
```
逐行把输出对应到main.go里的输入。若输出不一致，先直接对比函数返回值，再看调用方格式化。错误不一定是panic：有些错误通过第二返回值传给调用方处理。
修复后保留starter红灯记录与自己的绿灯记录，回答本文末尾的追问。观察题：画出参数、局部变量、返回值。Go断点操作要等IDE插件单独验收；本候选不能宣称已验证调试器，可用测试和打印先跟踪这三个值。此观察不伪装成自动评分通过。

## 5. 常见排错
- 找不到go.mod：在本题go目录运行，不能在课程根盲跑
- import未使用：不要删固定import；exercise.go中保留编译锚点让两种练习区实现共享import集合，生产代码通常只导入真正需要的包
- 刚改代码却读到旧绿灯：加-count=1；公共桥禁用Gradle缓存并核对具体子例名
- 测试文件改绿：不属于完成；测试与调用方是合同，修练习区
- 中文标点不同：字符串比较逐字节比较，中文逗号和英文逗号不相同
- 不知道如何恢复：完整答案在go/answers/*.go.txt；打开[作者源中的starter占位定义](../../../../overlay/go-course/core/quantity/task-info.yaml)，把go/exercise.go练习区替换为其中placeholder_text的内容，勿覆盖其他文件。学员预览目录不包含task-info.yaml，请使用此链接

## 分步练习与迁移观察：让坏输入有解释
1. 看`(int, error)`：这是两个返回值，不是Java的一个Tuple对象。临时写`return 12, nil`只会通过输入12的子例；它没有解析输入。比较`raw := " 12 "`与`n := 12`，一个是文本，一个可参与整数运算。
2. 在练习区声明`s := strings.TrimSpace(raw)`。先写空串分支；再用`for i := 0; i < len(s); i++`逐字节检查。`s[i]`是byte，`'0'`是字符常量。写好后跑空串、字母、正号三个子例，错误类别应稳定。
3. `n, err := strconv.Atoi(s)`后先处理err，再判1和1000上下界。任何错误都返回0；千万不要把出错时的n继续送到下游。跑上限、溢出、非ASCII数字子例，然后看完整调用方：continue只结束本次循环，所以一个坏输入不应阻止下一输入被报告。
4. 第二种答案不调用Atoi，用“乘10之前检查”的方法累积数值。用raw="101"逐轮手算n=1、10、101；用"1001"手算为什么最后一轮被拒。`err != nil`检查是否失败，`errors.Is(err, ErrQuantityRange)`判断失败类别。

## 本题逐步实现
先把字符串的外观（语法）检查完，再解析并检查业务范围。这样100000000000x不会因前缀过大而得到错误类别。手写方案在乘10之前证明结果仍不超过1000，所以机器int宽度不影响行为。

## Java对照
Java Integer.parseInt通常抛异常；Go strconv.Atoi同时返回(int,error)。短变量声明 n, err := ... 接收两个返回值，必须先处理err再相信n。nil error表示成功；errors.Is类似稳定的异常类型判断，不依赖中文错误文案。

## 提示H1–H4
- H1：先把合同中的正常输入手算一遍，再读TestContract同名子例
- H2：先把字符串的外观（语法）检查完，再解析并检查业务范围
- H3：阅读answers中第一种完整答案，标出每一个提前return对应的合同
- H4：逐行替换练习区，再对照第二种实现；不用修改import和测试也应全部通过

## 标准答案与解释

### stdlib
仅填入练习区：
```go
	s := strings.TrimSpace(raw)
	if s == "" { return 0, ErrInvalidQuantity }
	for i:=0; i<len(s); i++ { if s[i]<'0' || s[i]>'9' { return 0, ErrInvalidQuantity } }
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 || n > MaxQuantity { return 0, ErrQuantityRange }
	return n, nil
```
完整可比较源码见go/answers/stdlib.go.txt。

### manual
仅填入练习区：
```go
	s := strings.TrimSpace(raw)
	if s == "" { return 0, ErrInvalidQuantity }
	// 先完整检查语法，避免“很长的数字x”被错误分类为范围错误。
	for i:=0; i<len(s); i++ { if s[i]<'0' || s[i]>'9' { return 0, ErrInvalidQuantity } }
	n := 0
	for i:=0; i<len(s); i++ {
		digit := int(s[i]-'0')
		if n > (MaxQuantity-digit)/10 { return 0, ErrQuantityRange }
		n = n*10 + digit
	}
	if n == 0 { return 0, ErrQuantityRange }
	return n, nil
```
完整可比较源码见go/answers/manual.go.txt。

两种实现遵守同一合同，而不是两个不同预期。先把字符串的外观（语法）检查完，再解析并检查业务范围。这样100000000000x不会因前缀过大而得到错误类别。手写方案在乘10之前证明结果仍不超过1000，所以机器int宽度不影响行为。

## 面试递进与迁移
1. 为什么数字格式和业务范围要分开？调用方可能把两者展示为不同纠正建议。
2. 为什么不能丢弃Atoi的第二个返回值？溢出或坏输入时返回数值不能当合法数量。
3. 为什么逐字节可以检查本题输入？合同只允许ASCII数字；一般中文文本处理不能默认一个字节一个字符。
4. 迁移：若上限来自配置，应怎样把配置传入函数并验证负配置？先定义错误优先级，再扩展表驱动测试。

## 图示
![调用与返回](go/diagrams/flow.png)

## 验收边界
原矩阵用例数量是设计估算，不当已通过数。本候选每题一个Academy task，教学阶段不冒充三个已交互验收task。原生IDE导入、Check及Go调试仍NOT_RUN；Go/Java命令执行结果需要单独记录。
