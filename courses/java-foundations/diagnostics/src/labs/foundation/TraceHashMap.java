package labs.foundation;

import com.sun.jdi.*;
import com.sun.jdi.connect.*;
import com.sun.jdi.event.*;
import com.sun.jdi.request.*;

import java.util.*;

/** 通过JDI启动自己创建的有限子进程，记录真实方法入口；不开放远程调试地址。 */
public final class TraceHashMap {
    public static void main(String[] args) throws Exception {
        LaunchingConnector connector = Bootstrap.virtualMachineManager().defaultConnector();
        var arguments = connector.defaultArguments();
        arguments.get("main").setValue("labs.foundation.HashMapScenario");
        arguments.get("options").setValue("-Xmx64m -XX:ActiveProcessorCount=2 -cp " + args[0]);
        VirtualMachine vm = connector.launch(arguments);
        long deadline = System.nanoTime() + java.util.concurrent.TimeUnit.SECONDS.toNanos(20);
        List<String> lines = new ArrayList<>();
        try {
            ClassPrepareRequest prepare = vm.eventRequestManager().createClassPrepareRequest();
            prepare.addClassFilter("labs.foundation.HashMapScenario");
            prepare.setSuspendPolicy(EventRequest.SUSPEND_ALL);
            prepare.enable();
            // 由VMStartEvent的EventSet.resume启动，避免重复resume越过ClassPrepare断点。
            boolean active = true;
            int events = 0;
            while (active && System.nanoTime() < deadline && events < 5000) {
                EventSet set = vm.eventQueue().remove(500);
                if (set == null) continue;
                for (Event event : set) {
                    if (event instanceof ClassPrepareEvent loaded) {
                        Method begin = loaded.referenceType().methodsByName("begin").getFirst();
                        BreakpointRequest start =
                                vm.eventRequestManager().createBreakpointRequest(begin.location());
                        start.setSuspendPolicy(EventRequest.SUSPEND_ALL);
                        start.enable();
                    } else if (event instanceof BreakpointEvent start) {
                        start.request().disable();
                        for (String type :
                                List.of("java.util.HashMap", "java.util.HashMap$TreeNode")) {
                            MethodEntryRequest entry =
                                    vm.eventRequestManager().createMethodEntryRequest();
                            entry.addClassFilter(type);
                            entry.setSuspendPolicy(EventRequest.SUSPEND_EVENT_THREAD);
                            entry.enable();
                        }
                    } else if (event instanceof MethodEntryEvent entered) {
                        events++;
                        String name = entered.method().name();
                        if (!Set.of(
                                        "resize",
                                        "treeifyBin",
                                        "getTreeNode",
                                        "find",
                                        "split",
                                        "treeify",
                                        "untreeify")
                                .contains(name)) continue;
                        var scenario =
                                vm.classesByName("labs.foundation.HashMapScenario").getFirst();
                        ObjectReference target =
                                (ObjectReference) scenario.getValue(scenario.fieldByName("target"));
                        StackFrame frame = entered.thread().frame(0);
                        if (entered.method().declaringType().name().equals("java.util.HashMap")
                                && (frame.thisObject() == null
                                        || frame.thisObject().uniqueID() != target.uniqueID()))
                            continue;
                        if (entered.method()
                                .declaringType()
                                .name()
                                .equals("java.util.HashMap$TreeNode")) {
                            ObjectReference node = frame.thisObject();
                            Value key = node.getValue(node.referenceType().fieldByName("key"));
                            if (!(key instanceof ObjectReference reference)
                                    || !reference
                                            .referenceType()
                                            .name()
                                            .equals("labs.foundation.HashMapRoutes$Key")) continue;
                        }
                        ArrayReference table =
                                (ArrayReference)
                                        target.getValue(
                                                target.referenceType().fieldByName("table"));
                        Value phase = scenario.getValue(scenario.fieldByName("phase"));
                        Value size = target.getValue(target.referenceType().fieldByName("size"));
                        Value threshold =
                                target.getValue(target.referenceType().fieldByName("threshold"));
                        StringBuilder line =
                                new StringBuilder("phase=")
                                        .append(phase)
                                        .append(" method=")
                                        .append(entered.method().declaringType().name())
                                        .append('.')
                                        .append(name)
                                        .append(" capacity=")
                                        .append(table == null ? 0 : table.length())
                                        .append(" size=")
                                        .append(size)
                                        .append(" threshold=")
                                        .append(threshold);
                        try {
                            for (LocalVariable variable : frame.visibleVariables()) {
                                if (Set.of("hash", "bit", "index", "h", "lc", "hc")
                                        .contains(variable.name()))
                                    line.append(' ')
                                            .append(variable.name())
                                            .append('=')
                                            .append(frame.getValue(variable));
                            }
                        } catch (AbsentInformationException missing) {
                            line.append(" locals=NOT_AVAILABLE");
                        }
                        if (name.equals("untreeify")) {
                            StackFrame parent = entered.thread().frame(1);
                            try {
                                for (LocalVariable variable : parent.visibleVariables()) {
                                    if (Set.of("lc", "hc", "bit").contains(variable.name()))
                                        line.append(" split_")
                                                .append(variable.name())
                                                .append('=')
                                                .append(parent.getValue(variable));
                                }
                            } catch (AbsentInformationException missing) {
                                line.append(" split_locals=NOT_AVAILABLE");
                            }
                        }
                        lines.add(line.toString());
                    } else if (event instanceof VMDeathEvent
                            || event instanceof VMDisconnectEvent) {
                        active = false;
                    }
                }
                if (active) set.resume();
            }
            if (active) throw new IllegalStateException("调试未在资源预算内结束");
            for (String line : lines) System.out.println(line);
            System.out.println("TRACE_EVENTS=" + lines.size());
        } finally {
            try {
                vm.dispose();
            } catch (VMDisconnectedException ignored) {
            }
            Process process = vm.process();
            if (!process.waitFor(2, java.util.concurrent.TimeUnit.SECONDS))
                process.destroyForcibly();
            String targetOutput =
                    new String(
                            process.getInputStream().readAllBytes(),
                            java.nio.charset.StandardCharsets.UTF_8);
            System.out.println("TARGET_STDOUT=" + targetOutput.strip());
        }
    }
}
