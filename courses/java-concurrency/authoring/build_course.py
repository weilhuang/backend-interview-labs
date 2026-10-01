#!/usr/bin/env python3
"""中文课程的单一作者源；生成代码、公开答案、占位区和清单。"""
from pathlib import Path
import json, textwrap, yaml
ROOT=Path(__file__).resolve().parents[1]
SHA='890adb6410dab4606a4f26a942aed02fb2f55387'
TASKS=[]
def clean(s):return textwrap.dedent(s).strip()+'\n'
def task(slug,title,cls,source,test,usage,goals,concept,diagram,steps,source_files,source_notes,questions,mutation,alternative):
 TASKS.append(dict(slug=slug,title=title,cls=cls,source=clean(source),test=clean(test),usage=clean(usage),goals=goals,concept=concept,diagram=diagram,steps=steps,source_files=source_files,source_notes=source_notes,questions=questions,mutation=mutation,alternative=alternative))

task('01-publication','JMM：安全发布与复合原子性','PublicationLab',r'''
package labs;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public final class PublicationLab {
    public record Snapshot(int version, List<String> routes) {
        public Snapshot {
            if (version < 0) throw new IllegalArgumentException("版本不能为负");
            routes = List.copyOf(routes);
        }
    }
    private volatile Snapshot current = new Snapshot(0, List.of());
    private final AtomicInteger accepted = new AtomicInteger();
    public void publish(Snapshot next) {
        // 答案开始：发布
        current = Objects.requireNonNull(next, "配置不能为空");
        // 答案结束：发布
    }
    public Snapshot current() { return current; }
    public int accept() {
        // 答案开始：计数
        return accepted.incrementAndGet();
        // 答案结束：计数
    }
    public int accepted() { return accepted.get(); }

    // 教学反例：栅栏刻意让两个读都发生在写之前，即使 value 是 volatile 也会丢更新。
    public static int forcedLostUpdate() throws Exception {
        class Box { volatile int value; }
        Box box = new Box();
        CyclicBarrier bothRead = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Callable<Void> increment = () -> {
                int old = box.value;
                bothRead.await(2, TimeUnit.SECONDS);
                box.value = old + 1;
                return null;
            };
            Future<Void> first = pool.submit(increment), second = pool.submit(increment);
            first.get(3, TimeUnit.SECONDS); second.get(3, TimeUnit.SECONDS);
            return box.value;
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) throw new IllegalStateException("线程未退出");
        }
    }
}
''',r'''
import labs.PublicationLab;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
@Timeout(10)
class PublicationLabTest {
 @Test void publishedSnapshotDoesNotAliasCaller() {
  var routes = new ArrayList<>(List.of("/orders"));
  var lab = new PublicationLab();
  lab.publish(new PublicationLab.Snapshot(1, routes)); routes.clear();
  assertEquals(List.of("/orders"), lab.current().routes(), "发布的数据不能被调用者继续修改");
  assertThrows(UnsupportedOperationException.class, () -> lab.current().routes().add("/admin"));
  assertThrows(NullPointerException.class, () -> lab.publish(null));
  assertThrows(IllegalArgumentException.class, () -> new PublicationLab.Snapshot(-1,List.of()));
 }
 @Test void publishedPairRemainsOneSnapshot() throws Exception {
  var lab = new PublicationLab(); var entered = new CountDownLatch(1);
  try (var pool = Executors.newSingleThreadExecutor()) {
   Future<PublicationLab.Snapshot> read = pool.submit(() -> { entered.countDown(); return lab.current(); });
   assertTrue(entered.await(2,TimeUnit.SECONDS));
   var snapshot=read.get(2,TimeUnit.SECONDS);
   assertEquals(snapshot.version()==0?List.of():List.of("/v1"),snapshot.routes());
  }
  lab.publish(new PublicationLab.Snapshot(1,List.of("/v1")));
  assertEquals(1,lab.current().version());
 }
 @Test void eachAcceptedCallHasUniqueSequence() throws Exception {
  var lab = new PublicationLab(); var start = new CountDownLatch(1);
  try (var pool=Executors.newFixedThreadPool(4)) {
   var results=new ArrayList<Future<List<Integer>>>();
   for(int t=0;t<4;t++) results.add(pool.submit(()->{start.await();var out=new ArrayList<Integer>();for(int i=0;i<100;i++)out.add(lab.accept());return out;}));
   start.countDown(); var seen=new HashSet<Integer>();
   for(var f:results) seen.addAll(f.get(3,TimeUnit.SECONDS));
   assertEquals(400,seen.size());assertEquals(400,lab.accepted());assertTrue(seen.contains(1));assertTrue(seen.contains(400));
  }
 }
 @Test void volatileDoesNotMakeReadModifyWriteAtomic() throws Exception { assertEquals(1,PublicationLab.forcedLostUpdate()); }
}
''',r'''
package labs;
import java.util.List;
public final class PublicationLabUsage {
 public static void main(String[] args) throws Exception {
  var lab=new PublicationLab();lab.publish(new PublicationLab.Snapshot(1,List.of("/orders")));
  System.out.println("配置="+lab.current());System.out.println("受理序号="+lab.accept());
  System.out.println("受控错误计数="+PublicationLab.forcedLostUpdate());
 }
}
''',
'做一个路由快照发布器和受理计数器。调用者可修改原始列表，但已经发布的配置不能变化；一次读必须得到同一代完整快照。本课限定生命周期最多Integer.MAX_VALUE次accept，范围内每次返回从1开始的唯一序号；超长运行生产服务需另定溢出策略。并列完成受控丢更新反例。',
'可见性、原子性、有序性是三个问题。将不可变 Snapshot 经 volatile 引用发布，读者只读一次引用，再使用该快照，避免把两代配置的字段拼起来。record 的字段是 final，但 List 仍可能是可变对象，必须防御性复制。final 字段语义不能允许构造期间 this 逃逸，也不等同于自动发布所有后来写入。accepted.incrementAndGet 的线性化点由原子更新提供；volatile int 上的读取、加一、写回仍是多个动作。forcedLostUpdate 故意加栅栏，证明这个复合操作的逻辑漏洞，不是用同步工具“测试到真实弱内存重排”。',
'写者: 构造完整快照 --> volatile 写 current\n                              | happens-before\n读者:                  volatile 读 current --> 读取不可变字段\n\n错误计数: 甲读0 --+--> 甲写1\n                 |\n          乙读0 --+--> 乙写1   最终1，缺少一个完整的原子更新',
['先运行调用端，画出路由版本与列表的成对关系','填写 publish 与 accept；不要在读取端拆成两次 current() 后取不同字段','修改调用方原始列表，证明已发布快照不变','运行受控丢更新；去掉 volatile 是否修复？解释答案','画出程序次序、volatile synchronizes-with、传递关系；列出 Thread.start/join 和锁释放/获取的其他发布方式'],
['java/util/concurrent/atomic/AtomicInteger.java'],
'固定源码中追 AtomicInteger.incrementAndGet → Unsafe.getAndAddInt。不要把 Java 层没有显式循环误解为没有原子硬件/VM支持。对照 JLS21 17.4.5 与17.5：volatile边和final字段规则解决的前提不同。测试中的 Future.get/join 也产生可见性边，因此“读到了正确值”不能单独证明 publish 必须为volatile。字段删除volatile的弱内存错误只做O类审阅，不编造每次必失败的测试。需要 jcstress 时另建工具实验并记录JVM/架构/重复次数。',
[('机制','为什么一个 volatile 引用比两个 volatile 字段容易维护配置一致性？','两个字段可能来自不同更新。先构造不可变聚合，再单点替换，读者只获取一次。'),('边界','record 是否深不可变？','不是。其引用字段不能重新赋值，所引用对象仍可能可变。本例通过 List.copyOf 保存不可修改的元素引用；String 元素不可变，才满足当前深度。'),('取舍','AtomicInteger 与 synchronized 选哪个？','单变量原子更新适合前者；多个相关字段要共同维护不变量时，锁或不可变聚合CAS更直观。'),('追问','十万次没见到重排说明线程安全吗？','不能。测试覆盖的是一些执行，JMM约束的是所有允许执行。用规范证明发布，用压力工具收集补充观察。')],
[('routes = List.copyOf(routes);','routes = Objects.requireNonNull(routes);'),('return accepted.incrementAndGet();','return accepted.getAndIncrement();')],
[('private final AtomicInteger accepted = new AtomicInteger();','private int accepted;'),('public int accept() {','public synchronized int accept() {'),('return accepted.incrementAndGet();','return ++accepted;'),('public int accepted() { return accepted.get(); }','public synchronized int accepted() { return accepted; }')])

task('02-cancellation','线程生命周期：协作取消与有界关闭','CooperativeWorker',r'''
package labs;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
public final class CooperativeWorker {
 @FunctionalInterface public interface Work { void run() throws Exception; }
 private final CountDownLatch started=new CountDownLatch(1), stopped=new CountDownLatch(1);
 private final AtomicReference<Throwable> failure=new AtomicReference<>();
 private final Thread thread;
 public CooperativeWorker(Work work,Runnable cleanup) {
  Objects.requireNonNull(work);Objects.requireNonNull(cleanup);
  thread=Thread.ofPlatform().daemon().name("实验-可取消工作者").unstarted(()->{
   started.countDown();
   try { work.run(); }
   catch(InterruptedException cancelled) { Thread.currentThread().interrupt(); }
   catch(Throwable problem) { failure.set(problem); }
   finally {
    try { cleanup.run(); } catch(Throwable problem) { failure.compareAndSet(null,problem); }
    finally { stopped.countDown(); }
   }
  });
 }
 public void start() { thread.start(); }
 public boolean awaitStarted(Duration budget) throws InterruptedException { return started.await(nanos(budget),TimeUnit.NANOSECONDS); }
 public boolean awaitStopped(Duration budget) throws InterruptedException { return stopped.await(nanos(budget),TimeUnit.NANOSECONDS); }
 public boolean cancelAndAwait(Duration budget) throws InterruptedException {
  // 答案开始：取消
  long wait=nanos(budget);
  thread.interrupt();
  return stopped.await(wait,TimeUnit.NANOSECONDS);
  // 答案结束：取消
 }
 public Throwable failure() { return failure.get(); }
 public boolean alive() { return thread.isAlive(); }
 private static long nanos(Duration budget) {
  Objects.requireNonNull(budget);
  if(budget.isNegative())throw new IllegalArgumentException("预算不能为负");
  return budget.toNanos();
 }
}
''',r'''
import labs.CooperativeWorker;
import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
@Timeout(10)
class CooperativeWorkerTest {
 @Test void interruptClosesResourceExactlyOnce() throws Exception {
  var inside=new CountDownLatch(1);var block=new CountDownLatch(1);var cleaned=new AtomicInteger();
  var worker=new CooperativeWorker(()->{inside.countDown();block.await();},cleaned::incrementAndGet);
  worker.start();
  try {assertTrue(inside.await(2,TimeUnit.SECONDS));assertTrue(worker.cancelAndAwait(Duration.ofSeconds(2)));assertEquals(1,cleaned.get());assertNull(worker.failure());}
  finally {block.countDown();worker.cancelAndAwait(Duration.ofSeconds(2));}
 }
 @Test void ignoredSignalCannotBeReportedAsStopped() throws Exception {
  var entered=new CountDownLatch(1);var interrupted=new CountDownLatch(1);var release=new CountDownLatch(1);
  var worker=new CooperativeWorker(()->{entered.countDown();try{new CountDownLatch(1).await();}catch(InterruptedException expected){interrupted.countDown();release.await();}},()->{});
  worker.start();
  try {assertTrue(entered.await(2,TimeUnit.SECONDS));assertFalse(worker.cancelAndAwait(Duration.ZERO));assertTrue(interrupted.await(2,TimeUnit.SECONDS));assertTrue(worker.alive());}
  finally {release.countDown();assertTrue(worker.awaitStopped(Duration.ofSeconds(2)));}
 }
 @Test void failuresAreVisibleAndCleanupStillRuns() throws Exception {
  var cleaned=new AtomicBoolean();var expected=new IllegalStateException("模拟业务错误");
  var worker=new CooperativeWorker(()->{throw expected;},()->cleaned.set(true));worker.start();
  assertTrue(worker.awaitStopped(Duration.ofSeconds(2)));assertSame(expected,worker.failure());assertTrue(cleaned.get());
 }
 @Test void budgetValidationPrecedesSignal() {
  var worker=new CooperativeWorker(()->{},()->{});
  assertThrows(IllegalArgumentException.class,()->worker.cancelAndAwait(Duration.ofSeconds(-1)));
  assertThrows(NullPointerException.class,()->worker.cancelAndAwait(null));
 }
 @Test void startupAndDuplicateStartAreExplicit() throws Exception {
  var worker=new CooperativeWorker(()->{},()->{});worker.start();assertTrue(worker.awaitStarted(Duration.ofSeconds(2)));
  assertThrows(IllegalThreadStateException.class,worker::start);assertTrue(worker.awaitStopped(Duration.ofSeconds(2)));
 }
}
''',r'''
package labs;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
public final class CooperativeWorkerUsage {
 public static void main(String[] args)throws Exception {
  var ready=new CountDownLatch(1);
  var worker=new CooperativeWorker(()->{ready.countDown();new CountDownLatch(1).await();},()->System.out.println("资源已释放"));
  worker.start();ready.await();System.out.println("关闭完成="+worker.cancelAndAwait(Duration.ofSeconds(2)));
 }
}
''',
'实现任务终止控制器。必须先 start 再取消；重复 start 按 Thread 契约抛异常。cancelAndAwait 发出中断并在给定预算内等清理结束，零预算只发信号不等待；返回 true 表示工作和 cleanup 已完成。负预算/空预算报错。未响应中断的工作必须返回 false，不能 Thread.stop 或假装成功。',
'中断不是从任意位置强行跳出。await/sleep等阻塞方法可以抛 InterruptedException 并清除标记；本例在线程最外层收到取消后恢复标记，结束任务。若方法可继续 throws InterruptedException，通常直接传播；若作为 Runnable 边界不能抛，必须采用合适的取消策略，不能简单空 catch 后继续。stopped 在 cleanup 完成后 countDown，因此调用者观察到 true 才能依赖资源已经归还。daemon只作为坏实现测试的最后退出保险，不能当关闭策略。',
'NEW --start--> RUNNABLE --> 等待/工作\n                        | interrupt 协作信号\n                        v\n                  捕获取消/业务异常\n                        v\n                   finally 清理 --> stopped信号\n调用者: cancel --> 有界等待 --> 完成true / 尚未完成false',
['先从调用端运行一个等待中的工作者，观察清理先于关闭完成输出','实现取消方法：校验、发信号、有界等待，顺序不能倒置','对忽略第一次中断的工作者做对照：用第二个latch决定何时放行，不用sleep猜状态','让业务与cleanup分别抛异常，解释主故障保留策略','补充业务循环里的 Thread.currentThread().isInterrupted 检查，并给每个外部I/O设置自身超时'],
['java/lang/Thread.java','java/util/concurrent/CountDownLatch.java'],
'定位 Thread.interrupt、isInterrupted、interrupted，并对照 InterruptedException 清除状态的调用契约。Thread 的状态是快照：RUNNABLE不代表当下在CPU上运行，WAITING不等于死锁。CountDownLatch.Sync.tryReleaseShared 在计数降到0时传播释放；await成功让取消方看见cleanup的写入。本实验保留业务故障，cleanup异常仅在没有主故障时记录；生产系统可用suppressed保留两者。不能在此声称future.cancel(true)保证底层网络请求结束。',
[('机制','为什么先interrupt再await？','先通知被等待的工作停止，否则可能互相等待。等待结束条件是清理后的latch。'),('边界','捕获InterruptedException后何时恢复标记？','不能传播且上层可能查询标记时通常恢复；若彻底处理取消并有明确约定，也可结束生命周期。不能无条件吞掉然后继续。'),('取舍','为什么不只把线程设为daemon？','JVM能退出不代表写入/事务/资源已完成。必须显式生命周期与失败状态。'),('追问','取消HTTP调用仍不退出怎么办？','设置连接/读取/整个请求deadline，使用客户端取消API；诊断阻塞位置，拒绝无界join，不用强杀线程替代协议。')],
[('thread.interrupt();','// 故意漏发取消信号'),('return stopped.await(wait,TimeUnit.NANOSECONDS);','return true;')],
[('return stopped.await(wait,TimeUnit.NANOSECONDS);','if (stopped.getCount() == 0) return true;\n  return stopped.await(wait, TimeUnit.NANOSECONDS);')])

task('03-bounded-buffer','monitor与Condition：可关闭有界缓冲区','BoundedBuffers',r'''
package labs;
import java.util.*;
import java.util.concurrent.locks.*;
public final class BoundedBuffers {
 private BoundedBuffers(){}
 public interface Buffer<T> {
  void put(T value)throws InterruptedException;
  Optional<T> take()throws InterruptedException;
  void close();
  int size();
 }
 public static final class MonitorBuffer<T> implements Buffer<T> {
  private final int capacity;private final Deque<T> queue=new ArrayDeque<>();private boolean closed;
  public MonitorBuffer(int capacity){if(capacity<1)throw new IllegalArgumentException("容量必须为正");this.capacity=capacity;}
  public synchronized void put(T value)throws InterruptedException {
   // 答案开始：监视器放入
   Objects.requireNonNull(value);
   while(queue.size()==capacity&&!closed)wait();
   if(closed)throw new IllegalStateException("缓冲区已关闭");
   queue.addLast(value);notifyAll();
   // 答案结束：监视器放入
  }
  public synchronized Optional<T> take()throws InterruptedException {
   // 答案开始：监视器取出
   while(queue.isEmpty()&&!closed)wait();
   if(queue.isEmpty())return Optional.empty();
   T value=queue.removeFirst();notifyAll();return Optional.of(value);
   // 答案结束：监视器取出
  }
  public synchronized void close(){closed=true;notifyAll();}
  public synchronized int size(){return queue.size();}
 }
 public static final class LockBuffer<T> implements Buffer<T> {
  private final int capacity;private final Deque<T> queue=new ArrayDeque<>();
  private final ReentrantLock lock=new ReentrantLock();
  private final Condition notEmpty=lock.newCondition(),notFull=lock.newCondition();private boolean closed;
  public LockBuffer(int capacity){if(capacity<1)throw new IllegalArgumentException("容量必须为正");this.capacity=capacity;}
  public void put(T value)throws InterruptedException {
   // 答案开始：显式锁放入
   Objects.requireNonNull(value);lock.lockInterruptibly();
   try{while(queue.size()==capacity&&!closed)notFull.await();
    if(closed)throw new IllegalStateException("缓冲区已关闭");
    queue.addLast(value);notEmpty.signal();
   }finally{lock.unlock();}
   // 答案结束：显式锁放入
  }
  public Optional<T> take()throws InterruptedException {
   // 答案开始：显式锁取出
   lock.lockInterruptibly();
   try{while(queue.isEmpty()&&!closed)notEmpty.await();
    if(queue.isEmpty())return Optional.empty();
    T value=queue.removeFirst();notFull.signal();return Optional.of(value);
   }finally{lock.unlock();}
   // 答案结束：显式锁取出
  }
  public void close(){lock.lock();try{closed=true;notEmpty.signalAll();notFull.signalAll();}finally{lock.unlock();}}
  public int size(){lock.lock();try{return queue.size();}finally{lock.unlock();}}
 }
}
''',r'''
import static org.junit.jupiter.api.Assertions.*;

import labs.BoundedBuffers;

import org.junit.jupiter.api.*;

import java.util.*;
import java.util.concurrent.*;
import java.util.function.IntFunction;

@Timeout(12)
class BoundedBuffersTest {
    final List<IntFunction<BoundedBuffers.Buffer<Integer>>> factories =
            List.of(BoundedBuffers.MonitorBuffer::new, BoundedBuffers.LockBuffer::new);

    @Test
    void fifoCloseAndValidation() throws Exception {
        for (var factory : factories) {
            assertThrows(IllegalArgumentException.class, () -> factory.apply(0));
            var b = factory.apply(2);
            assertThrows(NullPointerException.class, () -> b.put(null));
            b.put(1);
            b.put(2);
            assertEquals(2, b.size());
            b.close();
            b.close();
            assertEquals(Optional.of(1), b.take());
            assertEquals(Optional.of(2), b.take());
            assertEquals(Optional.empty(), b.take());
            assertThrows(IllegalStateException.class, () -> b.put(3));
            assertEquals(0, b.size());
        }
    }

    @Test
    void closingWakesConsumersAndProducers() throws Exception {
        for (var factory : factories) {
            var empty = factory.apply(1);
            var full = factory.apply(1);
            full.put(1);
            var entered = new CountDownLatch(4);
            try (var pool = Executors.newFixedThreadPool(4)) {
                var consumers = new ArrayList<Future<Optional<Integer>>>();
                var producers = new ArrayList<Future<Boolean>>();
                for (int i = 0; i < 2; i++)
                    consumers.add(
                            pool.submit(
                                    () -> {
                                        entered.countDown();
                                        return empty.take();
                                    }));
                for (int i = 0; i < 2; i++)
                    producers.add(
                            pool.submit(
                                    () -> {
                                        entered.countDown();
                                        try {
                                            full.put(2);
                                            return false;
                                        } catch (IllegalStateException expected) {
                                            return true;
                                        }
                                    }));
                try {
                    assertTrue(entered.await(2, TimeUnit.SECONDS));
                    empty.close();
                    full.close();
                    for (var f : consumers)
                        assertEquals(Optional.empty(), f.get(2, TimeUnit.SECONDS));
                    for (var f : producers) assertTrue(f.get(2, TimeUnit.SECONDS));
                } finally {
                    empty.close();
                    full.close();
                    pool.shutdownNow();
                }
            }
        }
    }

    @Test
    void producersAndConsumerPreserveAllElements() throws Exception {
        for (var factory : factories) {
            var b = factory.apply(2);
            var start = new CountDownLatch(1);
            var pool = Executors.newFixedThreadPool(3);
            var completed = new ExecutorCompletionService<Set<Integer>>(pool);
            var futures = new ArrayList<Future<Set<Integer>>>();
            Throwable primary = null;
            try {
                var first =
                        completed.submit(
                                () -> {
                                    start.await();
                                    for (int i = 0; i < 40; i++) b.put(i);
                                    return null;
                                });
                var second =
                        completed.submit(
                                () -> {
                                    start.await();
                                    for (int i = 40; i < 80; i++) b.put(i);
                                    return null;
                                });
                var consumer =
                        completed.submit(
                                () -> {
                                    start.await();
                                    var seen = new HashSet<Integer>();
                                    Optional<Integer> x;
                                    while ((x = b.take()).isPresent())
                                        assertTrue(seen.add(x.get()), "不能重复消费");
                                    return seen;
                                });
                futures.addAll(List.of(first, second, consumer));
                start.countDown();
                int finishedProducers = 0;
                for (int i = 0; i < futures.size(); i++) {
                    var done = completed.poll(3, TimeUnit.SECONDS);
                    assertNotNull(done, "并发任务未按期限完成，请检查等待条件与通知");
                    // 按完成顺序传播错误：消费者的TODO不能被等待生产者的超时遮住。
                    var values = done.get();
                    if (done == consumer) {
                        assertEquals(80, values.size());
                    } else if (++finishedProducers == 2) {
                        b.close();
                    }
                }
            } catch (Exception | Error failure) {
                primary = failure;
                throw failure;
            } finally {
                Throwable cleanup = null;
                try {
                    b.close();
                } catch (Exception | Error failure) {
                    cleanup = failure;
                }
                try {
                    for (var future : futures) future.cancel(true);
                } catch (Exception | Error failure) {
                    cleanup = combine(cleanup, failure);
                }
                try {
                    pool.shutdownNow();
                    assertTrue(pool.awaitTermination(2, TimeUnit.SECONDS), "并发测试线程未正常结束");
                } catch (InterruptedException failure) {
                    Thread.currentThread().interrupt();
                    cleanup = combine(cleanup, failure);
                } catch (Exception | Error failure) {
                    cleanup = combine(cleanup, failure);
                }
                if (cleanup != null) {
                    if (primary != null) primary.addSuppressed(cleanup);
                    else if (cleanup instanceof Exception failure) throw failure;
                    else throw (Error) cleanup;
                }
            }
        }
    }

    private static Throwable combine(Throwable first, Throwable next) {
        if (first == null) return next;
        first.addSuppressed(next);
        return first;
    }

    @Test
    void interruptedWaiterDoesNotPoisonLock() throws Exception {
        for (var factory : factories) {
            var b = factory.apply(1);
            var entered = new CountDownLatch(1);
            var interrupted = new CountDownLatch(1);
            Thread waiter =
                    Thread.ofPlatform()
                            .daemon()
                            .start(
                                    () -> {
                                        entered.countDown();
                                        try {
                                            b.take();
                                        } catch (InterruptedException expected) {
                                            interrupted.countDown();
                                        }
                                    });
            try {
                assertTrue(entered.await(2, TimeUnit.SECONDS));
                waiter.interrupt();
                assertTrue(interrupted.await(2, TimeUnit.SECONDS));
                b.put(7);
                assertEquals(Optional.of(7), b.take());
            } finally {
                b.close();
                waiter.interrupt();
                waiter.join(2000);
                assertFalse(waiter.isAlive());
            }
        }
    }
}
''',r'''
package labs;
public final class BoundedBuffersUsage {
 public static void main(String[] args)throws Exception {
  for(BoundedBuffers.Buffer<String> b:java.util.List.<BoundedBuffers.Buffer<String>>of(new BoundedBuffers.MonitorBuffer<>(2),new BoundedBuffers.LockBuffer<>(2))){
   b.put("订单-1");b.put("订单-2");b.close();
   for(var value=b.take();value.isPresent();value=b.take())System.out.println(value.get());
   System.out.println("已排空且关闭");
  }
 }
}
''',
'为订单后台流水线写两种同契约有界队列。FIFO，不接收null，容量大于0。满时put等待，空时take等待。close幂等：拒绝新put，已有元素可继续取完；关闭且空时take返回Optional.empty。关闭必须唤醒所有等待者；中断可传播；不承诺公平排队。',
'条件队列里等待的是“可能有空间/数据”这件事，不是一次唤醒就永久获得资格。wait/await释放当前锁，返回前重新获取，所以醒来必须在while内重新判断。monitor只有一个wait set，notify可能叫醒不合适的一类等待者，参考解使用notifyAll。显式锁将notEmpty与notFull分组，正常单次操作signal对应等待组，close则对两组signalAll。公平锁不等于OS调度公平，且可能牺牲吞吐。两个版本共享的是契约，不是完全相同的中断能力：synchronized的锁获取本身不可中断，lockInterruptibly可以。',
'生产者 --持锁检查 满?--是--> notFull等待 --重新取锁--> 再检查\n                 |否\n                 v\n               入队 --signal--> notEmpty等待的消费者\n\nclose: 关闭标记 + 唤醒两类等待者\n       已有元素继续排空；空且关闭 -> 结束',
['先用容量2顺序put/take运行调用端，明确close不是清空','依次写MonitorBuffer.put/take并保证检查与修改都在同一把锁','写LockBuffer等价实现，把unlock放在finally','阅读测试中的满队列生产者/空队列消费者关闭场景，增加多等待者变体','画两把锁交叉获取的环路，提出全局锁顺序或缩小临界区方案，不在测试进程制造永久死锁'],
['java/util/concurrent/ArrayBlockingQueue.java','java/util/concurrent/locks/ReentrantLock.java','java/util/concurrent/locks/AbstractQueuedSynchronizer.java'],
'ArrayBlockingQueue.put/take的while、await和enqueue/dequeue对应本题容量不变量；该JDK队列本身没有此处的close协议，不能逐字替换。ReentrantLock.newCondition返回AQS.ConditionObject。追ConditionObject.await、signal、enableWait、acquire，区分条件队列与同步获取队列：signal把资格转为争锁，不是直接把锁交给对方。异常路径必须重新获得锁后再按约定抛出/恢复中断。源码私有字段随版本变化，本课只钉住21+35。',
[('机制','为什么if改成while有实质差别？','虚假唤醒、竞争者先拿走资源、关闭等都会使醒来时条件仍不满足，必须重新检查。'),('边界','close后为何还返回旧元素？','这是明确的排空式关闭契约。若业务要求立即丢弃，应新定义取消策略与丢弃回调。'),('取舍','notifyAll会不会有惊群？','会有额外唤醒和争锁；单wait set下更容易保证活性。Condition按条件分组减少无用唤醒。'),('追问','队列FIFO是否保证消费者按开始等待顺序服务？','不保证。元素顺序、锁公平性、线程调度是不同层次。')],
[('T value=queue.removeFirst();notifyAll();return Optional.of(value);','T value=queue.removeLast();notifyAll();return Optional.of(value);'),('if(closed)throw new IllegalStateException("缓冲区已关闭");','if(false)throw new IllegalStateException("缓冲区已关闭");')],
[('queue.addLast(value);notifyAll();','queue.offerLast(value);notifyAll();'),('T value=queue.removeFirst();notifyAll();return Optional.of(value);','T value=queue.pollFirst();notifyAll();return Optional.of(value);'),('queue.addLast(value);notEmpty.signal();','queue.offerLast(value);notEmpty.signalAll();')])

task('04-aqs','AQS源码：一次性门与共享同步','OneShotGate',r'''
package labs;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.AbstractQueuedSynchronizer;
public final class OneShotGate {
 private static final class Sync extends AbstractQueuedSynchronizer {
  protected int tryAcquireShared(int ignored) {
   // 答案开始：获取
   return getState()==1?1:-1;
   // 答案结束：获取
  }
  protected boolean tryReleaseShared(int ignored) {
   // 答案开始：打开
   return compareAndSetState(0,1);
   // 答案结束：打开
  }
  boolean opened(){return getState()==1;}
 }
 private final Sync sync=new Sync();
 public void open(){sync.releaseShared(1);}
 public boolean isOpen(){return sync.opened();}
 public void await()throws InterruptedException{sync.acquireSharedInterruptibly(1);}
 public boolean await(Duration budget)throws InterruptedException{
  Objects.requireNonNull(budget);if(budget.isNegative())throw new IllegalArgumentException("预算不能为负");
  return sync.tryAcquireSharedNanos(1,budget.toNanos());
 }
}
''',r'''
import labs.OneShotGate;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
@Timeout(10)
class OneShotGateTest {
 @Test void closedOpenIdempotentAndZeroBudget()throws Exception{
  var gate=new OneShotGate();assertFalse(gate.isOpen());assertFalse(gate.await(Duration.ZERO));
  gate.open();gate.open();assertTrue(gate.isOpen());assertTrue(gate.await(Duration.ZERO));
  assertThrows(IllegalArgumentException.class,()->gate.await(Duration.ofSeconds(-1)));
  assertThrows(NullPointerException.class,()->gate.await(null));
 }
 @Test void openReleasesEveryWaiterAndPublishesData()throws Exception{
  var gate=new OneShotGate();var ready=new CountDownLatch(4);int[] data={0};
  try(var pool=Executors.newFixedThreadPool(4)){
   var pending=new ArrayList<Future<Integer>>();for(int i=0;i<4;i++)pending.add(pool.submit(()->{ready.countDown();gate.await();return data[0];}));
   try{assertTrue(ready.await(2,TimeUnit.SECONDS));data[0]=42;gate.open();for(var f:pending)assertEquals(42,f.get(2,TimeUnit.SECONDS));}
   finally{gate.open();pool.shutdownNow();}
  }
 }
 @Test void interruptedWaiterDoesNotConsumeOpen()throws Exception{
  var gate=new OneShotGate();var ready=new CountDownLatch(1);var cancelled=new CountDownLatch(1);
  Thread waiter=Thread.ofPlatform().daemon().start(()->{ready.countDown();try{gate.await();}catch(InterruptedException expected){cancelled.countDown();}});
  try{assertTrue(ready.await(2,TimeUnit.SECONDS));waiter.interrupt();assertTrue(cancelled.await(2,TimeUnit.SECONDS));assertFalse(gate.isOpen());gate.open();assertTrue(gate.await(Duration.ZERO));}
  finally{gate.open();waiter.interrupt();waiter.join(2000);assertFalse(waiter.isAlive());}
 }
 @Test void permitsAndCompletionCountAreDifferent()throws Exception{
  var permits=new Semaphore(1);assertTrue(permits.tryAcquire());assertFalse(permits.tryAcquire());permits.release();assertEquals(1,permits.availablePermits());
  var done=new CountDownLatch(2);done.countDown();assertFalse(done.await(0,TimeUnit.NANOSECONDS));done.countDown();assertTrue(done.await(0,TimeUnit.NANOSECONDS));
 }
}
''',r'''
package labs;
import java.util.concurrent.*;
public final class OneShotGateUsage {
 public static void main(String[]args)throws Exception{
  var gate=new OneShotGate();var done=new CountDownLatch(2);var permits=new Semaphore(1);
  try(var pool=Executors.newFixedThreadPool(2)){
   for(int i=0;i<2;i++)pool.submit(()->{try{gate.await();permits.acquire();try{System.out.println("单许可执行区");}finally{permits.release();}}catch(InterruptedException e){Thread.currentThread().interrupt();}finally{done.countDown();}});
   gate.open();if(!done.await(2,TimeUnit.SECONDS))throw new IllegalStateException("任务未完成");
  }
  System.out.println("全部完成");
 }
}
''',
'教学实现一个只能从关闭变为打开的一次性门。open幂等并放行当前和未来所有等待者；await可中断；有界await超时返回false，零预算不阻塞；不支持重置、计数递减、独占所有者或Condition。随后用真实CountDownLatch记录完成数、Semaphore约束同时访问数。',
'AQS将状态语义留给子类，把竞争、排队、停放、唤醒、超时和中断取消集中处理。本题state只有0/1；tryAcquireShared负值失败，非负值成功，共享成功允许其他等待者继续。releaseShared在tryReleaseShared返回true时传播唤醒；只把state写成1却不走释放协议，等待者可能一直park。isOpen只用于观察，不可用“先isOpen再await”拼出额外保证。门只开一次，所以没有代际重置和ABA；把它当可复用CyclicBarrier是契约错误。',
'调用await --> tryAcquireShared(state) --成功--> 返回\n                    |失败\n                    v\n             AQS共享等待节点 --> park\n                    ^             |\nopen --> CAS 0到1 --> releaseShared唤醒 --> 重试获取\n\nCountDownLatch: 完成数降到0     Semaphore: 当前可用许可数',
['把门状态表写成0/1，列出所有合法转换','填写两个钩子，先通过零预算与幂等测试','让四个等待者看到open之前写入的42，并解释其发布关系','中断一个等待者后再open，确认取消没有消耗其他人的资格','跟进真实ReentrantLock获取失败入队路径，对比独占/共享与公平/非公平'],
['java/util/concurrent/locks/AbstractQueuedSynchronizer.java','java/util/concurrent/locks/ReentrantLock.java','java/util/concurrent/CountDownLatch.java','java/util/concurrent/Semaphore.java'],
'在21+35定位AQS.acquireSharedInterruptibly → tryAcquireShared/acquire；acquire统一路径处理中断、超时、队列链接、park与重试。定位releaseShared → tryReleaseShared → signalNext，查看shared节点如何继续传播；不要拿旧版教程的Node常量名称代替本版字段。ReentrantLock.NonfairSync.initialTryLock 与 Sync.tryRelease：非公平初次CAS、重入计数、最后一次释放清空owner是不同分支；FairSync检查队列前驱并不保证OS调度顺序。CountDownLatch.Sync状态是剩余次数，Semaphore.Sync状态是许可数；相同框架承载不同语义。提交一张“入口/失败条件/队列变化/唤醒后重检”的断点记录，不把本题两行钩子称为重写AQS。',
[('机制','AQS中的state到底是什么？','它只是受控整型状态，具体语义由同步器定义：锁重入数、latch剩余数、信号量许可数等不同。'),('边界','为什么不能给本门加reset就宣称可复用？','旧等待者、新等待者与代际状态会混淆；需要定义阶段、到达数和取消语义。'),('取舍','为什么业务更应优先CountDownLatch？','成熟API有完整契约、维护和测试。自定义同步器只有明确缺口时才值得额外验证成本。'),('追问','公平锁一定比非公平锁慢且绝不会饥饿吗？','不能绝对化。通常有额外排队开销；线程调度与工作负载仍影响完成顺序，性能要同条件测量。')],
[('return getState()==1?1:-1;','return 1;'),('return compareAndSetState(0,1);','return compareAndSetState(0,0);')],
[('return getState()==1?1:-1;','if (getState() == 0) return -1;\n   return 1;'),('return compareAndSetState(0,1);','if (getState() == 1) return false;\n   return compareAndSetState(0, 1);')])

task('05-atomics','CAS与并发容器：额度、ABA和热点计数','AtomicLedger',r'''
package labs;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.*;
public final class AtomicLedger {
 private final AtomicInteger balance;
 public AtomicLedger(int initial){if(initial<0)throw new IllegalArgumentException("余额不能为负");balance=new AtomicInteger(initial);}
 public boolean reserve(int amount){
  // 答案开始：CAS预留
  if(amount<=0)throw new IllegalArgumentException("预留数量必须为正");
  for(;;){int old=balance.get();if(old<amount)return false;if(balance.compareAndSet(old,old-amount))return true;}
  // 答案结束：CAS预留
 }
 public void add(int amount){
  if(amount<=0)throw new IllegalArgumentException("添加数量必须为正");
  for(;;){int old=balance.get();int next=Math.addExact(old,amount);if(balance.compareAndSet(old,next))return;}
 }
 public int balance(){return balance.get();}
 public static final class VersionedSlot {
  public record Snapshot(String value,int version){}
  private final AtomicStampedReference<String> value;
  public VersionedSlot(String initial){value=new AtomicStampedReference<>(Objects.requireNonNull(initial),0);}
  public Snapshot snapshot(){int[]stamp={0};String ref=value.get(stamp);return new Snapshot(ref,stamp[0]);}
  public boolean replace(Snapshot expected,String next){
   // 答案开始：防止ABA
   Objects.requireNonNull(expected);Objects.requireNonNull(next);
   return value.compareAndSet(expected.value(),next,expected.version(),Math.incrementExact(expected.version()));
   // 答案结束：防止ABA
  }
 }
 public static final class Counters {
  private final ConcurrentHashMap<String,LongAdder> counts=new ConcurrentHashMap<>();
  public void increment(String key){
   // 答案开始：并发计数
   counts.computeIfAbsent(Objects.requireNonNull(key),ignored->new LongAdder()).increment();
   // 答案结束：并发计数
  }
  public long count(String key){var counter=counts.get(Objects.requireNonNull(key));return counter==null?0:counter.sum();}
  public Map<String,Long> snapshot(){var copy=new TreeMap<String,Long>();counts.forEach((key,counter)->copy.put(key,counter.sum()));return Collections.unmodifiableMap(copy);}
 }
}
''',r'''
import labs.AtomicLedger;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
@Timeout(10)
class AtomicLedgerTest {
 @Test void reserveNeverOverdraws()throws Exception{
  var ledger=new AtomicLedger(100);var start=new CountDownLatch(1);var accepted=new AtomicInteger();
  try(var pool=Executors.newFixedThreadPool(4)){
   var jobs=new ArrayList<Future<?>>();for(int t=0;t<4;t++)jobs.add(pool.submit(()->{start.await();for(int i=0;i<50;i++)if(ledger.reserve(1))accepted.incrementAndGet();return null;}));
   start.countDown();for(var job:jobs)job.get(3,TimeUnit.SECONDS);
  }
  assertEquals(100,accepted.get());assertEquals(0,ledger.balance());assertFalse(ledger.reserve(1));ledger.add(3);assertTrue(ledger.reserve(3));assertEquals(0,ledger.balance());
 }
 @Test void validationAndOverflowPreserveState(){
  assertThrows(IllegalArgumentException.class,()->new AtomicLedger(-1));var l=new AtomicLedger(Integer.MAX_VALUE);
  assertThrows(IllegalArgumentException.class,()->l.reserve(0));assertThrows(IllegalArgumentException.class,()->l.add(-1));
  assertThrows(ArithmeticException.class,()->l.add(1));assertEquals(Integer.MAX_VALUE,l.balance());
 }
 @Test void abaIsRejectedByVersionEvenWhenReferenceReturns(){
  String a=new String("A"),b=new String("B");var plain=new AtomicReference<>(a);var old=plain.get();
  assertTrue(plain.compareAndSet(a,b));assertTrue(plain.compareAndSet(b,a));assertTrue(plain.compareAndSet(old,"旧操作仍成功"));
  var stamped=new AtomicLedger.VersionedSlot(a);var first=stamped.snapshot();
  assertTrue(stamped.replace(first,b));assertTrue(stamped.replace(stamped.snapshot(),a));
  assertSame(a,stamped.snapshot().value());assertEquals(2,stamped.snapshot().version());assertFalse(stamped.replace(first,"旧操作必须失败"));
 }
 @Test void completedCountersHaveExactTotals()throws Exception{
  var counts=new AtomicLedger.Counters();assertEquals(0,counts.count("不存在"));
  try(var pool=Executors.newFixedThreadPool(4)){var work=new ArrayList<Future<?>>();for(int t=0;t<4;t++)work.add(pool.submit(()->{for(int i=0;i<100;i++){counts.increment("订单");counts.increment("付款");}}));for(var f:work)f.get(3,TimeUnit.SECONDS);}
  assertEquals(Map.of("订单",400L,"付款",400L),counts.snapshot());
  assertThrows(UnsupportedOperationException.class,()->counts.snapshot().put("错误",1L));assertThrows(NullPointerException.class,()->counts.increment(null));
 }
}
''',r'''
package labs;
public final class AtomicLedgerUsage {
 public static void main(String[]args){
  var ledger=new AtomicLedger(3);System.out.println("预留2="+ledger.reserve(2));System.out.println("再次预留2="+ledger.reserve(2));
  var slot=new AtomicLedger.VersionedSlot("A");var old=slot.snapshot();slot.replace(old,"B");slot.replace(slot.snapshot(),old.value());
  System.out.println("旧版本更新="+slot.replace(old,"C"));
  var counts=new AtomicLedger.Counters();counts.increment("订单");System.out.println("计数="+counts.snapshot());
 }
}
''',
'实现不透支额度预留、带版本更新槽和并发热点计数。reserve只接受正数，不足不改状态；add溢出不改状态。版本槽的expected来自snapshot，值比较遵循引用身份，stamp递增且溢出报错。计数不提供运行中的原子全局快照，所有写者结束后才要求精确最终合计。',
'CAS只保证比较和替换这一瞬间，不保证“读取→计算→一次尝试”必然成功，所以失败要基于新值重算。预留的线性化点是成功CAS；余额不足时的读取也界定这次失败可发生的时刻。不要把数据库扣库存换成进程内AtomicInteger：重启、多个实例、持久化都没有覆盖。ABA不是值错误，而是只比较值无法识别中间历史。本槽将引用和版本一起比较，明确版本溢出边界。LongAdder把竞争分散到多个单元，sum不是对所有并发更新的原子快照，因此不能拿它的sum先检查再扣钱。',
'读取余额old --> 检查足够? --否--> 返回false\n       |是\n       v\n CAS(old, old-amount) --失败--> 重新读取\n       |成功\n       v\n    返回true\n\n仅引用: A --> B --> A  旧A仍匹配\n带版本: A/0 --> B/1 --> A/2  旧A/0不匹配',
['运行额度调用端，列出非法参数和溢出后的状态要求','写CAS重试；注意不能把减法放在循环外复用旧计算','用顺序固定的A→B→A验证ABA，不依赖线程调度碰运气','完成CHM的computeIfAbsent+LongAdder计数，等所有Future完成后核对合计','设计AtomicLong/LongAdder的同负载JMH对照，仅作为O任务，记录读写比、线程数、预热/fork；禁止以必须快若干倍判分'],
['java/util/concurrent/atomic/AtomicInteger.java','java/util/concurrent/atomic/AtomicStampedReference.java','java/util/concurrent/atomic/LongAdder.java','java/util/concurrent/atomic/Striped64.java','java/util/concurrent/ConcurrentHashMap.java'],
'追AtomicStampedReference内部不可变Pair与casPair：版本和值共同发布；引用比较不是String.equals。LongAdder.add先尝试base/已有Cell更新，冲突进入Striped64.longAccumulate；sum遍历base与cells，不是锁住所有写者的读取。ConcurrentHashMap.computeIfAbsent按槽状态走空槽CAS、预留或桶内同步等路径，回调要短，不能假设全表互斥；本例map不删除计数器。如果允许并发remove，已经取得旧LongAdder的线程可能更新脱离map的计数器，必须重新定义业务协议。',
[('机制','CAS失败为何必须重读？','竞争者已改变前置状态，旧余额计算不再代表当前条件。'),('边界','版本号永远解决ABA吗？','不。有限位宽可能回绕，外部系统可能重用版本。本题用incrementExact拒绝溢出，真实系统需更长期的唯一代际策略。'),('取舍','LongAdder能否作为余额？','不适合需要线性化检查扣减的不变量；适合高竞争统计。sum并非运行时原子快照。'),('追问','ConcurrentHashMap有了线程安全为何if(!containsKey)put仍会错？','单次操作安全不等于复合业务原子。使用putIfAbsent/compute或更大事务边界。')],
[('if(old<amount)return false;','if(old<amount)return true;'),('return value.compareAndSet(expected.value(),next,expected.version(),Math.incrementExact(expected.version()));','var actual=snapshot();return value.compareAndSet(expected.value(),next,actual.version(),Math.incrementExact(actual.version()));'),('ignored->new LongAdder()).increment();','ignored->new LongAdder()).add(2);')],
[('public boolean reserve(int amount){','public synchronized boolean reserve(int amount){'),('for(;;){int old=balance.get();if(old<amount)return false;if(balance.compareAndSet(old,old-amount))return true;}','int old=balance.get();if(old<amount)return false;balance.set(old-amount);return true;'),('public void add(int amount){','public synchronized void add(int amount){'),('for(;;){int old=balance.get();int next=Math.addExact(old,amount);if(balance.compareAndSet(old,next))return;}','balance.set(Math.addExact(balance.get(),amount));')])

task('06-executor','线程池：饱和、拒绝、异常与关闭','BoundedExecutor',r'''
package labs;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public final class BoundedExecutor {
 private final ThreadPoolExecutor pool;
 public BoundedExecutor(int core,int max,int queueCapacity){
  if(core<1||max<core||queueCapacity<1)throw new IllegalArgumentException("线程和队列容量非法");
  AtomicInteger ids=new AtomicInteger();
  pool=new ThreadPoolExecutor(core,max,30,TimeUnit.SECONDS,new ArrayBlockingQueue<>(queueCapacity),
    task->Thread.ofPlatform().daemon().name("实验-有界池-"+ids.incrementAndGet()).unstarted(task),new ThreadPoolExecutor.AbortPolicy());
 }
 public <T> Future<T> submit(Callable<T> job){return pool.submit(Objects.requireNonNull(job));}
 public boolean cancelQueued(Future<?> job){
  // 答案开始：取消清理
  boolean cancelled=Objects.requireNonNull(job).cancel(true);pool.purge();return cancelled;
  // 答案结束：取消清理
 }
 public boolean shutdown(Duration grace)throws InterruptedException{
  // 答案开始：有界关闭
  Objects.requireNonNull(grace);if(grace.isNegative())throw new IllegalArgumentException("预算不能为负");
  pool.shutdown();
  if(pool.awaitTermination(grace.toNanos(),TimeUnit.NANOSECONDS))return true;
  for(Runnable abandoned:pool.shutdownNow())if(abandoned instanceof Future<?> future)future.cancel(false);
  return pool.isTerminated();
  // 答案结束：有界关闭
 }
 public boolean awaitStopped(Duration budget)throws InterruptedException{
  Objects.requireNonNull(budget);if(budget.isNegative())throw new IllegalArgumentException("预算不能为负");
  return pool.awaitTermination(budget.toNanos(),TimeUnit.NANOSECONDS);
 }
 public int queued(){return pool.getQueue().size();}
 public int workers(){return pool.getPoolSize();}
}
''',r'''
import labs.BoundedExecutor;
import java.time.Duration;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
@Timeout(10)
class BoundedExecutorTest {
 @Test void coreThenQueueThenMaxThenReject()throws Exception{
  var pool=new BoundedExecutor(1,2,1);var coreStarted=new CountDownLatch(1);var maxStarted=new CountDownLatch(1);var release=new CountDownLatch(1);
  try{
   var one=pool.submit(()->{coreStarted.countDown();release.await();return 1;});assertTrue(coreStarted.await(2,TimeUnit.SECONDS));
   var two=pool.submit(()->2);assertEquals(1,pool.queued());
   var three=pool.submit(()->{maxStarted.countDown();release.await();return 3;});assertTrue(maxStarted.await(2,TimeUnit.SECONDS));assertEquals(2,pool.workers());
   assertThrows(RejectedExecutionException.class,()->pool.submit(()->4),"必须显式拒绝，不能静默丢弃");
   release.countDown();assertEquals(1,one.get(2,TimeUnit.SECONDS));assertEquals(2,two.get(2,TimeUnit.SECONDS));assertEquals(3,three.get(2,TimeUnit.SECONDS));
  }finally{release.countDown();pool.shutdown(Duration.ofSeconds(2));assertTrue(pool.awaitStopped(Duration.ofSeconds(2)));}
 }
 @Test void cancelledQueueSlotIsReusable()throws Exception{
  var pool=new BoundedExecutor(1,1,1);var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
  try{
   var running=pool.submit(()->{entered.countDown();release.await();return 0;});assertTrue(entered.await(2,TimeUnit.SECONDS));
   var queued=pool.submit(()->1);assertTrue(pool.cancelQueued(queued));assertTrue(queued.isCancelled());assertEquals(0,pool.queued());
   var replacement=pool.submit(()->2);release.countDown();assertEquals(0,running.get(2,TimeUnit.SECONDS));assertEquals(2,replacement.get(2,TimeUnit.SECONDS));
  }finally{release.countDown();pool.shutdown(Duration.ofSeconds(2));assertTrue(pool.awaitStopped(Duration.ofSeconds(2)));}
 }
 @Test void taskFailureIsObservedThroughFuture()throws Exception{
  var pool=new BoundedExecutor(1,1,1);
  try{var f=pool.submit(()->{throw new IllegalStateException("业务失败");});var e=assertThrows(ExecutionException.class,()->f.get(2,TimeUnit.SECONDS));assertInstanceOf(IllegalStateException.class,e.getCause());}
  finally{pool.shutdown(Duration.ofSeconds(2));assertTrue(pool.awaitStopped(Duration.ofSeconds(2)));}
 }
 @Test void forcedShutdownCompletesAbandonedFutures()throws Exception{
  var pool=new BoundedExecutor(1,1,1);var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
  try{
   pool.submit(()->{entered.countDown();release.await();return 1;});assertTrue(entered.await(2,TimeUnit.SECONDS));var queued=pool.submit(()->2);
   pool.shutdown(Duration.ZERO);assertTrue(queued.isCancelled(),"shutdownNow取出的Future也要结束");
   assertThrows(RejectedExecutionException.class,()->pool.submit(()->3));assertTrue(pool.awaitStopped(Duration.ofSeconds(2)));
  }finally{release.countDown();pool.shutdown(Duration.ofSeconds(2));}
 }
 @Test void parameters(){assertThrows(IllegalArgumentException.class,()->new BoundedExecutor(2,1,1));assertThrows(IllegalArgumentException.class,()->new BoundedExecutor(1,1,0));}
}
''',r'''
package labs;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
public final class BoundedExecutorUsage {
 public static void main(String[]args)throws Exception{
  var pool=new BoundedExecutor(1,2,2);
  try{var future=pool.submit(()->"订单已校验");System.out.println(future.get(2,TimeUnit.SECONDS));}
  finally{pool.shutdown(Duration.ofSeconds(2));System.out.println("池已退出="+pool.awaitStopped(Duration.ofSeconds(2)));}
 }
}
''',
'构建可复用有界执行器：先核心线程，再有界队列，再最大线程，超过容量抛RejectedExecutionException。Future显式传递业务异常。取消队列任务要回收队列容量。优雅预算耗尽后shutdownNow，并结束从队列取出的Future；返回false表示仍有任务未退出，不能声称中断已杀死所有任务。',
'线程池控制的是线程与排队策略，不是业务成功保障。submit把任务包装为FutureTask，异常存入Future，若无人get/监听可能失去可见性。无界队列常使maximumPoolSize在通常饱和路径不生效：任务总能入队，就不会走扩展非核心线程的分支。CallerRunsPolicy会把延迟传递给提交方，可能在事件循环或持锁线程造成问题；DiscardPolicy可能让submit返回的Future永不完成。本课程使用AbortPolicy，业务层必须把拒绝转成明确响应或有界重试。shutdownNow只尽力中断运行任务，返回未启动任务；本封装还要cancel其Future。',
'提交任务\n   |\n工作者 < core? --是--> 新核心线程\n   |否\n队列 offer成功? --是--> 排队 + 复查运行状态\n   |否\n工作者 < max? --是--> 新非核心线程\n   |否\n明确拒绝\n\n关闭: shutdown -> 有界等待 -> shutdownNow + 取消未启动Future',
['运行正常调用端，再读精确饱和测试中的三个latch步骤','配置ArrayBlockingQueue与AbortPolicy，不允许换成默认无界队列','实现cancelQueued，验证取消后新任务能立即占用空位','实现两阶段关闭；区分已接收、已开始、已完成、已取消四个状态','新增一个永不配合取消但由测试latch最终释放的任务，说明false的意义和应用级升级策略'],
['java/util/concurrent/ThreadPoolExecutor.java','java/util/concurrent/FutureTask.java','java/util/concurrent/AbstractExecutorService.java'],
'逐段追ThreadPoolExecutor.execute的三步：addWorker(command,true)、workQueue.offer后复查、addWorker(command,false)/reject。看ctl如何组合runState与workerCount，不自行依赖私有位数。沿addWorker → Worker → runWorker → getTask，记录异常如何影响worker退出；再跟AbstractExecutorService.submit → newTaskFor → FutureTask.run/setException/get，解释为何submit异常通常不会直接到uncaughtExceptionHandler。关闭看interruptIdleWorkers、interruptWorkers、drainQueue；本课补上返回队列Future的取消，不宣称标准shutdownNow自动使每个Future进入终态。',
[('机制','core=1/max=2/queue=1时第四个阻塞任务为何拒绝？','第1个占核心，第2个占队列，第3个扩最大线程，第4个无队列和工作者空间。'),('边界','Future.cancel(true)返回true等于代码已经退出吗？','不是。Future进入取消状态与底层协作停止是不同事件，仍要等待资源清理。'),('取舍','为什么不能只加大队列？','排队延迟、内存和超时放大；要根据服务率、deadline和背压策略定容量。'),('追问','应用关闭后还有数据库写入怎么办？','停止接单，跟踪在途，设置I/O期限与幂等补偿；先确认运行任务是否响应中断，不把进程存活当交付成功。')],
[('new ThreadPoolExecutor.AbortPolicy()','new ThreadPoolExecutor.DiscardPolicy()'),('pool.purge();','/* 故意不清理取消项 */'),('future.cancel(false);','{ /* 故意遗漏队列Future终态 */ }')],
[('pool.purge();','pool.getQueue().removeIf(item -> item instanceof Future<?> f && f.isCancelled());')])

task('07-futures','异步聚合：截止时间、降级、隔离与上下文','AsyncGateway',r'''
package labs;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.*;
import java.util.function.Supplier;
public final class AsyncGateway {
 public record Summary(String primary,String secondary){}
 @FunctionalInterface public interface Ticket { void cancel(); }
 @FunctionalInterface public interface Timer { Ticket schedule(Duration delay,Runnable action); }
 public static final class RealTimer implements Timer,AutoCloseable {
  private final ScheduledExecutorService scheduler=Executors.newSingleThreadScheduledExecutor(r->Thread.ofPlatform().daemon().name("实验-期限计时器").unstarted(r));
  public Ticket schedule(Duration delay,Runnable action){var future=scheduler.schedule(action,nanos(delay),TimeUnit.NANOSECONDS);return ()->future.cancel(false);}
  public void close(){scheduler.shutdownNow();}
 }
 public static CompletableFuture<Summary> aggregate(CompletableFuture<String> primary,CompletableFuture<String> secondary,Duration budget,Timer timer){
  // 答案开始：有界聚合
  Objects.requireNonNull(primary);Objects.requireNonNull(secondary);Objects.requireNonNull(timer);nanos(budget);
  var result=new CompletableFuture<Summary>();
  Ticket alarm=timer.schedule(budget,()->result.completeExceptionally(new TimeoutException("聚合已超过预算")));
  result.whenComplete((value,error)->alarm.cancel());
  primary.whenComplete((value,error)->{if(error!=null)result.completeExceptionally(error);});
  primary.thenCombine(secondary.exceptionally(error->"次要服务降级"),Summary::new)
    .whenComplete((value,error)->{if(error==null)result.complete(value);else result.completeExceptionally(error);});
  return result;
  // 答案结束：有界聚合
 }
 private final Executor executor;private final Semaphore permits;private final ThreadLocal<String> request=new ThreadLocal<>();
 public AsyncGateway(Executor executor,int concurrency){this.executor=Objects.requireNonNull(executor);if(concurrency<1)throw new IllegalArgumentException("并发上限必须为正");permits=new Semaphore(concurrency);}
 public String currentRequest(){return request.get();}
 public <T> CompletableFuture<T> request(String id,Supplier<T> action){
  // 答案开始：隔离和上下文
  Objects.requireNonNull(id);Objects.requireNonNull(action);var result=new CompletableFuture<T>();
  if(!permits.tryAcquire()){result.completeExceptionally(new RejectedExecutionException("下游隔离舱已满"));return result;}
  try{executor.execute(()->{
   String previous=request.get();request.set(id);
   try{result.complete(action.get());}catch(Throwable error){result.completeExceptionally(error);}
   finally{if(previous==null)request.remove();else request.set(previous);permits.release();}
  });}catch(RuntimeException rejected){permits.release();result.completeExceptionally(rejected);}
  return result;
  // 答案结束：隔离和上下文
 }
 private static long nanos(Duration budget){Objects.requireNonNull(budget);if(budget.isNegative())throw new IllegalArgumentException("预算不能为负");return budget.toNanos();}
}
''',r'''
import labs.AsyncGateway;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
@Timeout(10)
class AsyncGatewayTest {
 static final class ManualTimer implements AsyncGateway.Timer{
  Runnable action;boolean cancelled;Duration delay;
  public AsyncGateway.Ticket schedule(Duration delay,Runnable action){this.delay=delay;this.action=action;return ()->cancelled=true;}
  void expire(){if(!cancelled)action.run();}
 }
 @Test void parallelResultsCombineAndCancelAlarm(){
  var timer=new ManualTimer();var first=new CompletableFuture<String>();var second=new CompletableFuture<String>();
  var combined=AsyncGateway.aggregate(first,second,Duration.ofSeconds(1),timer);
  second.complete("库存");assertFalse(combined.isDone());first.complete("订单");
  assertEquals(new AsyncGateway.Summary("订单","库存"),combined.join());assertTrue(timer.cancelled);timer.expire();assertFalse(combined.isCompletedExceptionally());
 }
 @Test void optionalFailureDegradesButPrimaryFailureFailsImmediately(){
  var timer=new ManualTimer();var primary=new CompletableFuture<String>();var optional=new CompletableFuture<String>();
  var result=AsyncGateway.aggregate(primary,optional,Duration.ofSeconds(1),timer);optional.completeExceptionally(new IllegalStateException("推荐故障"));primary.complete("订单");
  assertEquals("次要服务降级",result.join().secondary());
  var critical=new CompletableFuture<String>();var pending=new CompletableFuture<String>();
  var failed=AsyncGateway.aggregate(critical,pending,Duration.ofSeconds(1),new ManualTimer());critical.completeExceptionally(new IllegalArgumentException("订单失败"));
  assertTrue(failed.isDone());assertInstanceOf(IllegalArgumentException.class,assertThrows(CompletionException.class,failed::join).getCause());assertFalse(pending.isDone());
 }
 @Test void deadlineDoesNotPretendToInterruptUpstream(){
  var timer=new ManualTimer();var primary=new CompletableFuture<String>();var optional=new CompletableFuture<String>();
  var result=AsyncGateway.aggregate(primary,optional,Duration.ZERO,timer);timer.expire();
  assertInstanceOf(TimeoutException.class,assertThrows(CompletionException.class,result::join).getCause());assertFalse(primary.isCancelled());assertFalse(optional.isDone());
  primary.complete("太晚");optional.complete("太晚");assertTrue(result.isCompletedExceptionally());
 }
 @Test void contextIsClearedEvenAfterFailureAndPermitsAreReturned(){
  var jobs=new ArrayDeque<Runnable>();var gateway=new AsyncGateway(jobs::add,1);
  var first=gateway.request("请求甲",()->{assertEquals("请求甲",gateway.currentRequest());throw new IllegalStateException("模拟错误");});
  var rejected=gateway.request("请求乙",()->2);assertInstanceOf(RejectedExecutionException.class,assertThrows(CompletionException.class,rejected::join).getCause());
  jobs.remove().run();assertTrue(first.isCompletedExceptionally());assertNull(gateway.currentRequest(),"线程复用前必须清除上下文");
  var next=gateway.request("请求丙",()->gateway.currentRequest());jobs.remove().run();assertEquals("请求丙",next.join());assertNull(gateway.currentRequest());
 }
 @Test void executorRejectionDoesNotLeakPermit(){
  var count=new java.util.concurrent.atomic.AtomicInteger();var gateway=new AsyncGateway(job->{if(count.getAndIncrement()==0)throw new RejectedExecutionException("执行器拒绝");job.run();},1);
  assertTrue(gateway.request("甲",()->1).isCompletedExceptionally());assertEquals(2,gateway.request("乙",()->2).join());
 }
 @Test void aggregateTimeoutKeepsBulkheadOccupiedUntilRealWorkFinishes()throws Exception{
  var entered=new CountDownLatch(1);var release=new CountDownLatch(1);var timer=new ManualTimer();
  try(var pool=Executors.newSingleThreadExecutor()){
   var gateway=new AsyncGateway(pool,1);
   var slow=gateway.request("请求甲",()->{entered.countDown();try{release.await();}catch(InterruptedException error){Thread.currentThread().interrupt();throw new CompletionException(error);}return "结果";});
   try{
    assertTrue(entered.await(2,TimeUnit.SECONDS));
    var aggregate=AsyncGateway.aggregate(slow,CompletableFuture.completedFuture("推荐"),Duration.ofSeconds(1),timer);timer.expire();
    assertTrue(aggregate.isCompletedExceptionally());assertFalse(slow.isDone());
    assertTrue(gateway.request("请求乙",()->"不能进入").isCompletedExceptionally());
    release.countDown();assertEquals("结果",slow.get(2,TimeUnit.SECONDS));
    pool.submit(()->{}).get(2,TimeUnit.SECONDS);
    assertEquals("恢复",gateway.request("请求丙",()->"恢复").get(2,TimeUnit.SECONDS));
   }finally{release.countDown();}
  }
 }
 @Test void cancelledResultStillNeedsUnderlyingCleanup(){
  var jobs=new ArrayDeque<Runnable>();var gateway=new AsyncGateway(jobs::add,1);var ran=new java.util.concurrent.atomic.AtomicBoolean();
  var pending=gateway.request("甲",()->{ran.set(true);return 1;});assertTrue(pending.cancel(true));jobs.remove().run();assertTrue(ran.get());assertNull(gateway.currentRequest());
  var next=gateway.request("乙",()->2);jobs.remove().run();assertEquals(2,next.join());
 }
}
''',r'''
package labs;
import java.time.Duration;
import java.util.concurrent.*;
public final class AsyncGatewayUsage {
 public static void main(String[]args)throws Exception{
  try(var pool=Executors.newFixedThreadPool(2);var timer=new AsyncGateway.RealTimer()){
   var gateway=new AsyncGateway(pool,2);
   var order=gateway.request("请求-42",()->"订单:"+gateway.currentRequest());
   var recommendation=gateway.<String>request("请求-42",()->{throw new IllegalStateException("推荐暂不可用");});
   System.out.println(AsyncGateway.aggregate(order,recommendation,Duration.ofSeconds(2),timer).get(3,TimeUnit.SECONDS));
  }
 }
}
''',
'做一个两下游聚合：主服务失败立即失败；次服务失败提供明确降级字符串；必须两者成功/降级且在总预算内才返回Summary。超时只结束聚合结果，不声称底层已取消。使用注入Timer做确定性测试，生产调用用RealTimer。异步请求使用显式Executor和Semaphore隔离，并在复用线程上设置与清理请求ID。',
'CompletableFuture描述完成依赖，不天然拥有底层阻塞操作。orTimeout、completeOnTimeout或本题的计时器都不能自动中止HTTP客户端；如需取消，应另持有客户端请求句柄并把剩余预算传给连接、读、请求各层。thenCombine需要双方结果，本题额外监听主服务错误，避免主失败却继续等可选服务。回调默认可在完成线程执行，不能在其中偷偷做耗时阻塞。隔离舱在任务提交前拿许可，执行器拒绝也必须归还；任务完成/异常finally恢复原上下文以兼容嵌套调用。',
'主服务 --------------------+--> thenCombine --> 聚合结果\n   |失败即终止              |\n次服务 --> 失败转显式降级 --+\n                              ^\n总预算计时器 --超时异常---------+\n\n请求ID + 许可 --> 显式执行器 --> 设置上下文 --> 业务\n                                          | finally\n                                     恢复上下文 + 归还许可',
['先运行调用端得到含降级的Summary，确认主/次服务的业务差异','实现aggregate，通过手动timer.expire测试截止时间，不等待真实秒数','让主服务失败而次服务永远pending，验证主失败立即可见','实现隔离与上下文，测试排队线程复用、业务异常、执行器拒绝','取消返回的CompletableFuture，观察底层仍执行；写出客户端级取消与剩余deadline传播方案'],
['java/util/concurrent/CompletableFuture.java','java/util/concurrent/ThreadLocalRandom.java','java/lang/ThreadLocal.java'],
'定位CompletableFuture.uniWhenComplete、biApply/biApplyStage、completeExceptionally、cancel和orTimeout。完成节点登记与结果CAS决定谁赢得完成竞态；失败不会回滚其他下游已经发生的副作用。读取源码中cancel的mayInterruptIfRunning说明：它不是像FutureTask那样拥有运行线程。ThreadLocal.remove走ThreadLocalMap.remove/expungeStaleEntry，弱引用key也不意味着value立即释放。此处通过显式remove/恢复值避免请求串号；InheritableThreadLocal在线程池中不等价于逐请求上下文传播。',
[('机制','为什么超时之后主服务仍可能写数据库？','完成future和停止外部操作是两条控制链；超时结果不会撤销副作用。需要deadline、显式取消和幂等业务协议。'),('边界','所有异常都降级合理吗？','不。合同区分核心依赖和可选依赖，权限/数据损坏等不能随意伪造成成功。'),('取舍','为什么不用默认commonPool？','阻塞I/O可能占满共享池并干扰无关任务；显式执行器能控制容量与生命周期。'),('追问','ThreadLocal.clear放在成功分支够吗？','不够，异常和取消路径也会复用线程。finally恢复原值可支持嵌套调用。')],
[('new TimeoutException("聚合已超过预算")','new IllegalStateException("错误的超时类型")'),('if(previous==null)request.remove();else request.set(previous);','/* 故意泄漏上下文 */'),('permits.release();result.completeExceptionally(rejected);','result.completeExceptionally(rejected);')],
[('secondary.exceptionally(error->"次要服务降级")','secondary.handle((value,error)->error==null?value:"次要服务降级")')])

task('08-virtual-threads','虚拟线程：资源约束与事故证据','VirtualGateway',r'''
package labs;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public final class VirtualGateway implements AutoCloseable {
 private final ExecutorService executor=Executors.newVirtualThreadPerTaskExecutor();
 private final Semaphore downstream,admission;
 private final Set<FutureTask<?>> active=ConcurrentHashMap.newKeySet();
 public VirtualGateway(int concurrency,int acceptedLimit){
  if(concurrency<1||concurrency>16||acceptedLimit<concurrency||acceptedLimit>64)throw new IllegalArgumentException("实验限制为1到16个下游并发、最多64个受理任务");
  downstream=new Semaphore(concurrency);admission=new Semaphore(acceptedLimit);
 }
 public <T> Future<T> submit(Callable<T> action){
  // 答案开始：资源受限的虚拟线程任务
  Objects.requireNonNull(action);
  if(!admission.tryAcquire())throw new RejectedExecutionException("受理上限已满");
  FutureTask<T> task=new FutureTask<>(()->{
   downstream.acquire();
   try{return action.call();}finally{downstream.release();}
  }){
   // 0=尚未启动，1=run正在执行，2=实际结束或在启动前取消。
   private final AtomicInteger phase=new AtomicInteger();
   private void releaseAdmission(){active.remove(this);admission.release();}
   public void run(){
    if(!phase.compareAndSet(0,1))return;
    try{super.run();}finally{phase.set(2);releaseAdmission();}
   }
   protected void done(){
    // 运行中取消只结束Future；许可必须等真正的run退出才归还。
    if(phase.compareAndSet(0,2))releaseAdmission();
   }
  };
  active.add(task);
  try{executor.execute(task);}catch(RuntimeException rejected){task.cancel(false);throw rejected;}
  return task;
  // 答案结束：资源受限的虚拟线程任务
 }
 public int availableDownstream(){return downstream.availablePermits();}
 public void close()throws InterruptedException{
  for(var task:active)task.cancel(true);executor.shutdownNow();
  if(!executor.awaitTermination(2,TimeUnit.SECONDS))throw new IllegalStateException("有任务未响应取消，请检查外部I/O超时");
 }
}
''',r'''
import labs.VirtualGateway;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
@Timeout(12)
class VirtualGatewayTest {
 @Test void virtualThreadsStillHonorDownstreamBound()throws Exception{
  var ready=new CountDownLatch(2);var release=new CountDownLatch(1);var running=new AtomicInteger();var maximum=new AtomicInteger();
  try(var gateway=new VirtualGateway(2,6)){
   var tasks=new ArrayList<Future<Integer>>();
   try{
    for(int i=0;i<6;i++){final int id=i;tasks.add(gateway.submit(()->{assertTrue(Thread.currentThread().isVirtual());int active=running.incrementAndGet();maximum.accumulateAndGet(active,Math::max);ready.countDown();try{release.await();return id;}finally{running.decrementAndGet();}}));}
    assertTrue(ready.await(2,TimeUnit.SECONDS));assertEquals(0,gateway.availableDownstream());assertThrows(RejectedExecutionException.class,()->gateway.submit(()->7));
    release.countDown();int sum=0;for(var task:tasks)sum+=task.get(3,TimeUnit.SECONDS);assertEquals(15,sum);assertEquals(2,maximum.get());assertEquals(2,gateway.availableDownstream());
   }finally{release.countDown();}
  }
 }
 @Test void cancellationAndExceptionReturnPermits()throws Exception{
  var started=new CountDownLatch(1);var release=new CountDownLatch(1);var cleaned=new CountDownLatch(1);
  try(var gateway=new VirtualGateway(1,3)){
   var running=gateway.submit(()->{started.countDown();try{release.await();return 1;}finally{cleaned.countDown();}});
   try{assertTrue(started.await(2,TimeUnit.SECONDS));var waiting=gateway.submit(()->2);assertTrue(waiting.cancel(true));assertTrue(running.cancel(true));assertTrue(cleaned.await(2,TimeUnit.SECONDS));
    var next=gateway.submit(()->{throw new IllegalStateException("业务故障");});assertInstanceOf(IllegalStateException.class,assertThrows(ExecutionException.class,()->next.get(2,TimeUnit.SECONDS)).getCause());
    var finalTask=gateway.submit(()->3);assertEquals(3,finalTask.get(2,TimeUnit.SECONDS));assertEquals(1,gateway.availableDownstream());
   }finally{release.countDown();}
  }
 }
 @Test void cancelledFutureDoesNotReleaseAdmissionUntilActionActuallyExits()throws Exception{
  var entered=new CountDownLatch(1);var sawInterrupt=new CountDownLatch(1);var release=new CountDownLatch(1);
  try(var gateway=new VirtualGateway(1,1)){
   var future=gateway.submit(()->{
    entered.countDown();
    try{release.await();}catch(InterruptedException cancelled){sawInterrupt.countDown();release.await();}
    return 1;
   });
   try{
    assertTrue(entered.await(2,TimeUnit.SECONDS));assertTrue(future.cancel(true));assertTrue(sawInterrupt.await(2,TimeUnit.SECONDS));
    assertTrue(future.isDone());assertEquals(0,gateway.availableDownstream());
    assertThrows(RejectedExecutionException.class,()->gateway.submit(()->2),"Future取消不能提前释放实际受理容量");
   }finally{release.countDown();}
  }
 }
 @Test void closeRejectsNewWork()throws Exception{
  var gateway=new VirtualGateway(1,1);gateway.close();assertThrows(RejectedExecutionException.class,()->gateway.submit(()->1));
 }
 @Test void boundsPreventAccidentalLargeLoad(){assertThrows(IllegalArgumentException.class,()->new VirtualGateway(0,1));assertThrows(IllegalArgumentException.class,()->new VirtualGateway(17,20));assertThrows(IllegalArgumentException.class,()->new VirtualGateway(1,65));}
}
''',r'''
package labs;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
public final class VirtualGatewayUsage {
 public static void main(String[]args)throws Exception{
  try(var gateway=new VirtualGateway(2,8)){
   var tasks=new ArrayList<Future<String>>();for(int i=0;i<8;i++){int id=i;tasks.add(gateway.submit(()->"订单"+id+"，虚拟线程="+Thread.currentThread().isVirtual()));}
   for(var task:tasks)System.out.println(task.get(2,TimeUnit.SECONDS));
  }
 }
}
''',
'用Java21稳定虚拟线程执行阻塞式请求，并保留下游并发与受理上限。每个请求一个虚拟线程，不把虚拟线程池化；实验最大16下游并发/64受理任务。permit只围绕真正下游调用，异常和中断都释放；close有界等待且拒绝新任务。随后运行安全诊断脚本采集本实验进程的线程转储与JFR。',
'虚拟线程降低的是大量阻塞任务持有平台线程的代价，不增加CPU核心数、连接池大小或数据库服务率。把慢下游的排队从平台线程移到虚拟线程仍可能积压，所以额外限制受理数和真正下游并发。Java21中，在synchronized区域内执行某些阻塞操作可能pin住carrier；这个结论必须标明版本，不能套到已改善相关行为的后来JDK。本题Future取消会使Future先终结，底层调用若忽略中断仍持有下游许可与受理许可。本实现区分尚未启动取消与运行中取消：前者立即归还一次，后者等run的finally实际退出再归还一次；不能用isDone证明外部资源已释放。',
'受理许可(最多64) --> 每任务虚拟线程 --> 下游许可(最多16) --> 阻塞I/O\n                              |等待时可卸载                 |\n                              +----------------------------+\n                                                    finally归还许可\n\n虚拟线程调度器 --> 少量carrier平台线程\nCPU繁忙 / 锁阻塞 / 连接池耗尽：证据不同，不能只数线程',
['运行调用端，确认Thread.isVirtual为true且输出结果顺序由调用方get决定','填写submit，区分受理许可和下游许可；提交被拒绝也不能泄漏许可','运行受控并发测试，6请求同时受理但最多2进入下游','运行scripts/diagnose.py，仅对它启动的隔离JVM采集；读取docs/诊断证据.md','用相同请求数/同一等待行为做平台池与虚拟线程对照，记录吞吐/延迟与环境；本任务不预设虚拟线程一定更快'],
['java/lang/VirtualThread.java','java/util/concurrent/ThreadPerTaskExecutor.java','java/util/concurrent/FutureTask.java','java/util/concurrent/Semaphore.java'],
'固定21+35追VirtualThread.runContinuation、park、unpark、mount/unmount、onPinned，区分虚拟线程与承载它的carrier。ThreadPerTaskExecutor.execute/submit为每个任务创建线程，不是复用固定worker队列；FutureTask.cancel可能改变状态并中断runner，done回调发生不等于call已退出。Semaphore.acquireSharedInterruptibly维持下游容量。JEP444与JDK21文档是本节版本依据；记录jdk.VirtualThreadPinned事件需实际遇到相关阻塞且满足阈值，“没有事件”不能推导“程序不存在pinning”。脚本默认不制造无界锁死/无限CPU/OOM。',
[('机制','为什么虚拟线程通常适合阻塞服务？','阻塞时可释放carrier去运行其他虚拟线程，从而支持较多并发等待；具体阻塞是否可卸载要看JDK和操作。'),('边界','换成虚拟线程就能去掉连接池吗？','不能。数据库连接、内存、远端吞吐仍有上限，保留容量保护和deadline。'),('取舍','CPU密集任务会因此快很多吗？','不会凭空增加核数。还要考虑调度、数据共享和测量条件。'),('追问','线程转储里很多WAITING就是故障吗？','正常排队也会WAITING。结合栈、资源拥有者、队列容量、请求时间和JFR判断活性问题。')],
[('downstream.acquire();','/* 故意不获取下游许可 */'),('Executors.newVirtualThreadPerTaskExecutor()','Executors.newCachedThreadPool(r->Thread.ofPlatform().daemon().unstarted(r))'),('if(phase.compareAndSet(0,2))releaseAdmission();','releaseAdmission();')],
[('private final AtomicInteger phase=new AtomicInteger();','private int phase;'),
 ('if(!phase.compareAndSet(0,1))return;','synchronized(this){if(phase!=0)return;phase=1;}'),
 ('finally{phase.set(2);releaseAdmission();}','finally{synchronized(this){phase=2;}releaseAdmission();}'),
 ('if(phase.compareAndSet(0,2))releaseAdmission();','boolean returnPermit; synchronized(this){returnPermit=phase==0;if(returnPermit)phase=2;}if(returnPermit)releaseAdmission();')])

import re, argparse, hashlib, os, subprocess
parser=argparse.ArgumentParser(description="从单一作者源生成规范格式的课程")
parser.add_argument('--formatter',type=Path,default=Path(os.environ.get('JAVA_FORMAT_JAR','/workspace/shared/academy-verification-deps/google-java-format-1.24.0-all-deps.jar')))
args=parser.parse_args()
if not args.formatter.is_file():raise SystemExit('缺少google-java-format1.24.0 all-deps.jar；请从官方Maven取得并用--formatter指定')
assert hashlib.sha256(args.formatter.read_bytes()).hexdigest()=='812f805f58112460edf01bf202a8e61d0fd1f35c0d4fabd54220640776ec57a1'
format_root=ROOT/'build/format-input';format_root.mkdir(parents=True,exist_ok=True)
format_files=[]
for item in TASKS:
 raw=item['source'];alternative=raw
 for old,new in item['alternative']:
  assert old in alternative,(item['cls'],old);alternative=alternative.replace(old,new)
 variants={'source':raw,'test':item['test'],'usage':item['usage'],'alternative':alternative}
 for index,(old,new) in enumerate(item['mutation']):
  assert old in raw,(item['cls'],old);variants[f'mutant-{index}']=raw.replace(old,new)
 item['formatted_paths']={}
 for role,contents in variants.items():
  target=format_root/(item['cls']+'-'+role+'.java');target.write_text(contents);format_files.append(str(target));item['formatted_paths'][role]=target
java=str(Path(os.environ['JAVA_HOME'])/'bin/java') if os.environ.get('JAVA_HOME') else 'java'
subprocess.run([java,'-jar',str(args.formatter),'--aosp','--replace']+format_files,check=True,timeout=60)
for item in TASKS:
 for role in ['source','test','usage']:item[role]=item['formatted_paths'][role].read_text()

def write(path,content):
 target=ROOT/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content,encoding='utf-8')
def dump(path,data):write(path,yaml.safe_dump(data,allow_unicode=True,sort_keys=False,width=110))
manifest=[]
for i,item in enumerate(TASKS,1):
 slug,title,cls=item['slug'],item['title'],item['cls'];rel=f'juc/{slug}/lab';src=item['source'];placeholders=[]
 for m in re.finditer(r'(?<=\n)([ \t]*)// 答案开始：[^\n]+\n(.*?)\n\1// 答案结束：[^\n]+',src,re.S):
  start,end=m.span(2);placeholders.append(dict(offset=len(src[:start].encode('utf-16-le'))//2,length=len(src[start:end].encode('utf-16-le'))//2,placeholder_text=m.group(1)+'throw new UnsupportedOperationException("TODO：请实现本段契约");'))
 assert placeholders,cls
 source=f'src/labs/{cls}.java';usage=f'src/labs/{cls}Usage.java';testfile=f'test/{cls}Test.java'
 write(f'{rel}/{source}',src);write(f'{rel}/{usage}',item['usage']);write(f'{rel}/{testfile}',item['test'])
 alternative=item['formatted_paths']['alternative'].read_text()
 write(f'{rel}/solution/Alternative.java.txt',alternative)
 mutation_files=[]
 for index in range(len(item['mutation'])):
  mutant_path=f'authoring/mutants/{cls}-{index}.java.txt'
  write(mutant_path,item['formatted_paths'][f'mutant-{index}'].read_text());mutation_files.append(mutant_path)
 dump(f'juc/{slug}/lesson-info.yaml',dict(custom_name=f'C02-{i:02d} · {title}',content=['lab']))
 dump(f'{rel}/task-info.yaml',dict(type='edu',custom_name=f'{i:02d} · {title}',files=[dict(name=source,visible=True,placeholders=placeholders),dict(name=usage,visible=True),dict(name=testfile,visible=True),dict(name='solution/Alternative.java.txt',visible=True)]))
 links='\n'.join(f'- [{name.split("/")[-1]}](https://github.com/openjdk/jdk/blob/{SHA}/src/java.base/share/classes/{name})' for name in item['source_files'])
 steps='\n'.join(f'{j}. {s}' for j,s in enumerate(item['steps'],1))
 questions='\n\n'.join(f'### {j}. {kind}：{q}\n\n参考表达：{a}' for j,(kind,q,a) in enumerate(item['questions'],1))
 doc=f'''# C02-{i:02d} · {title}

预计90–150分钟；源码证据和独立迁移另留30–60分钟。主线统一完整JDK21、Gradle8.10.2、JUnit Jupiter5.11.4 / Platform1.11.4；不需要前端、Docker、数据库或外部账号。源码基线与当前运行JVM补丁版本分别记录。

## 先用起来：企业场景与接口合同

{item['goals']}

作者工程保存完整参考实现；Academy学员占位区/普通学员副本从可编译的UnsupportedOperationException起步。完整答案、调用方与全部测试都随课提供。你可以先看答案再回测，但请把提示辅助与独立完成分开记录。

## 完整项目与运行入口

```text
{slug}/lab/
+-- src/labs/{cls}.java          # 实现接口与作者答案区
+-- src/labs/{cls}Usage.java     # 真实main调用方
+-- test/{cls}Test.java          # 全部可见契约测试
+-- solution/Alternative.java.txt # 另一种正确写法
+-- task.md                     # 教学步骤、源码、答案与追问
```

在课程根运行：

```sh
./gradlew :juc-{slug}-lab:test
./gradlew :juc-{slug}-lab:run
```

IDE中打开课程根或导入已由插件生成的课程归档；选项目SDK21和Gradle JVM21。普通源代码zip不是Academy归档。Check、提示、重置、归档导入的验证状态见根目录阶段报告，不能由命令行通过替代。

## 完整调用示例

```java
{item['usage']}```

先预测调用结果，再执行与测试比较。跨线程日志先后除非由代码建立关系，否则不构成契约；本课不按偶然调度顺序评分。

## 核心原理与ASCII图解

{item['concept']}

```text
{item['diagram']}
```

## 写代码、使用接口、验证结果

{steps}

先写清不变量，再填写答案区，先跑单任务test，再run，最后根目录test。测试红色时区分编译/合同错误、环境无效、超时未退出；不要通过加sleep、无限增大超时或删断言“修好”并发。测试的2–3秒等待只是死锁/调度故障护栏，不是性能SLA。

## 可选提示

<div class="hint" title="H1：找到关键状态">
列出哪些状态必须一起变化，哪些API只提供单次原子性。先看失败测试中的最小输入和前置条件。
</div>
<div class="hint" title="H2：跟随最小交错">
按照上图模拟成功、失败、关闭、取消四条路径；检查所有资源从哪里获得、在哪里归还。
</div>
<div class="hint" title="H3：对照局部机制">
先写合同校验，再实现状态转换。等待用条件循环，资源清理用finally；具体适用性以本节完整接口为准。
</div>
<div class="hint" title="H4：完整参考解">
下方公开标准解与Alternative文件可直接阅读；无需先通过题目。
</div>

## 真实源码定位与机制分析（R）

固定OpenJDK21 GA tag jdk-21+35，已核对commit {SHA}。正式API行为以Java21文档为准，私有实现只在这个commit下讲解。若运行的是21u修补版，必须把版本差异写入证据，不能伪称调试的就是GA二进制。

{links}

{item['source_notes']}

源码练习：打开对应原始文件，按上文符号设置断点或用IDE静态导航，记录“输入→入口→关键分支→状态变化→调用方观察”。记录失败/取消路径而不只截图类名。本课没有预制伪造断点截图；静态源码核对与动态调试分开填写。

## 标准答案与逐步解析

```java
{src}```

解析顺序：
1. 对照接口合同确认非法输入在修改状态前被拒绝
2. 逐行标出线性化点或发布边；不存在单一原子快照的地方要明确注明
3. 追踪等待/取消/失败路径与finally资源清理，解释何时真正完成
4. 读全部测试，指出每个断言保障哪个合同；参考实现并不是唯一合法字段布局
5. 对照公开Alternative.java.txt，再考虑新的边界；替代解是回归对照，不要求强制模仿某一风格

本单元具体算法与复杂度边界以上文机制和源码为准。阻塞等待的耗时取决于外部进展，不能因为方法体短就宣称“最坏O(1)且一定完成”；锁或CAS也不能保证每个线程在固定时间内获胜。

## 自动验收与观察验收分开

- A：本节所有可见JUnit测试；作者质量门禁还运行未填写起点和已知错误变体，确认测试能发现问题
- O：提交源码路线、happens-before/资源图、一次失败原因链及迁移说明；性能、调度、JFR样本均为证据，不按固定快慢判分
- R：原始源码commit、文件、符号与实际观察一致；只有静态阅读时明确标“动态断点未运行”
- T：自写模型只承诺本节接口；没有宣称实现完整JDK同步器、分布式事务或生产调度器

证据文件可按docs/证据模板.md填写。正确性测试通过不等于机制理解或源码任务完成。环境缺失记BLOCKED，没运行记NOT_RUN，不能汇总为PASS。

## 面试题递进与参考表达

{questions}

## 独立迁移与完成标准

不看答案重新实现一种业务变体：保持本节安全不变量，增加一个明确的失败或关闭条件，并写最小测试击穿旧实现。回答“新增条件改变了哪个状态机、哪些等待者必须被通知、哪些完成信号可靠”。24小时后重写关键方法，记录是否需要提示。

完成条件：A全通过；机制、边界、证据、独立迁移各能给可检验说明。任何资源泄漏、静默丢任务、错误成功或不受限等待仍未解决则不完成。源代码仅用于合成实验数据，不对用户真实服务注入故障。
'''
 write(f'{rel}/task.md',doc)
 manifest.append(dict(task=rel,**{key:item[key] for key in ['cls','mutation']},source=source,usage=usage,test=testfile,alternative='solution/Alternative.java.txt',mutation_files=mutation_files))

write('authoring/manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
dump('juc/section-info.yaml',dict(custom_name='Java并发：从不变量到真实JUC源码',content=[t['slug'] for t in TASKS]))
additional=['README.md','阶段报告.md','build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat','gradle/wrapper/gradle-wrapper.properties','gradle/wrapper/gradle-wrapper.jar','LICENSE-JetBrains-template','THIRD_PARTY_NOTICES.md','docs/证据模板.md','docs/诊断证据.md','docs/源码路线图.md','docs/实际调试记录.md','scripts/diagnose.py','scripts/ConcurrencyDiagnostics.java','scripts/BoundedBlockingComparison.java']
dump('course-info.yaml',dict(type='marketplace',title='Java后端面试实验室：Java并发与JUC',language='Chinese',summary='八个完整实验覆盖JMM、取消、有界缓冲区、AQS、CAS、线程池、异步期限与Java21虚拟线程；全部测试、调用端、标准解和源码路线公开可见。',programming_language='Java',content=['juc'],environment_settings={'jvm_language_level':'JDK_21'},additional_files=[dict(name=n,**({'is_binary':True} if n.endswith('.jar') else {})) for n in additional],yaml_version=2))
print('已生成',len(TASKS),'单元，答案和占位区来自同一源')
