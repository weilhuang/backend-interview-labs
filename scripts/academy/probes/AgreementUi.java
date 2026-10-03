import java.awt.GraphicsEnvironment;
import java.awt.Rectangle;
import java.awt.Robot;
import java.awt.event.InputEvent;
import java.awt.event.KeyEvent;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Properties;
import java.util.concurrent.TimeUnit;
import javax.imageio.ImageIO;

/** 本次专用 Xvfb；有限审图坐标或固定 Enter，不接收文本与任意命令。 */
class AgreementUi {
    interface CheckedStep { void run() throws Exception; }
    interface Snapshot { byte[] read() throws Exception; }
    static int[] profilePoint(String horizontal, String vertical) {
        if (!horizontal.matches("[0-9]{1,4}") || !vertical.matches("[0-9]{1,3}")) throw new IllegalArgumentException("本次审图坐标不符");
        int x=Integer.parseInt(horizontal),y=Integer.parseInt(vertical);
        if (x>=1280 || y>=900) throw new IllegalArgumentException("本次审图坐标越界");
        return new int[]{x,y};
    }
    static void profileClick(CheckedStep ownership, CheckedStep cancellation, CheckedStep click) throws Exception {
        ownership.run(); cancellation.run(); click.run();
    }
    static void finalTrustClick(CheckedStep finalProbe, Snapshot image, String approvedSha, CheckedStep click) throws Exception {
        finalProbe.run();
        // No blocking metadata probe may follow this final whole-image comparison.
        if (!sha(image.read()).equals(approvedSha)) throw new IllegalStateException("信任画面在最后核验期间变化");
        click.run();
    }
    private static byte[] capture(Robot robot, Rectangle bounds) throws Exception {
        var output = new ByteArrayOutputStream();
        if (!ImageIO.write(robot.createScreenCapture(bounds), "png", output)) {
            throw new IllegalStateException("PNG 编码不可用");
        }
        return output.toByteArray();
    }
    private static String sha(byte[] data) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
    }
    private static void verifyOwned(Path binding) throws Exception {
        Properties expected = new Properties();
        try (var stream = Files.newInputStream(binding)) { expected.load(stream); }
        if (!expected.getProperty("authority.path").equals(System.getenv("XAUTHORITY"))) throw new IllegalStateException("授权文件路径变化");
        if (!expected.getProperty("display").equals(System.getenv("DISPLAY"))) throw new IllegalStateException("显示器编号变化");
        String[] kinds=expected.containsKey("terminal.pid") ? new String[]{"wrapper","server","ide","terminal"} : new String[]{"wrapper","server","ide"};
        for (String kind : kinds) {
            String pid = expected.getProperty(kind+".pid");
            String fd = expected.getProperty(kind+".fd");
            if (!pid.matches("[0-9]+") || !fd.matches("[0-9]+")) throw new IllegalStateException("进程标识不符");
            // 继承Python已验证的pidfd；未reap的退出进程仍可能保留Pid，故还须拒绝stat的Z/X终态。
            String info = Files.readString(Path.of("/proc/self/fdinfo",fd));
            String livePid = info.lines().filter(line -> line.startsWith("Pid:")).findFirst().orElseThrow().substring(4).trim();
            if (!pid.equals(livePid)) throw new IllegalStateException("自有进程句柄已退出或变化");
            Path proc = Path.of("/proc",pid);
            String raw = Files.readString(proc.resolve("stat"));
            String[] fields = raw.substring(raw.lastIndexOf(')')+1).trim().split("\\s+");
            if (fields[0].equals("Z") || fields[0].equals("X")) throw new IllegalStateException("自有进程已退出");
            String[] keys = {"ppid","pgrp","session","start_time"};
            int[] positions = {1,2,3,19};
            for (int i=0;i<keys.length;i++) {
                if (!expected.getProperty(kind+"."+keys[i]).equals(fields[positions[i]])) throw new IllegalStateException("自有进程身份变化");
            }
            if (!expected.getProperty(kind+".uid").equals(Files.getAttribute(proc,"unix:uid").toString())) throw new IllegalStateException("进程UID变化");
        }
        for (String kind : new String[]{"socket","authority"}) {
            Path path=Path.of(expected.getProperty(kind+".path"));
            for (String key : new String[]{"dev","ino","uid"}) {
                if (!expected.getProperty(kind+"."+key).equals(Files.getAttribute(path,"unix:"+key,java.nio.file.LinkOption.NOFOLLOW_LINKS).toString())) throw new IllegalStateException("显示器文件身份变化");
            }
        }
    }
    static final class ModalComparison {
        final int x,y,width,height;
        final String dialogSha,fullSha,proofSha;
        final String line;
        ModalComparison(String value,String approvedFull) {
            if (!value.matches("MODAL1 [0-9]{1,4} [0-9]{1,3} [0-9]{1,4} [0-9]{1,3} [0-9a-f]{64} [0-9a-f]{64} [0-9a-f]{64}\\n")) throw new IllegalArgumentException("模态证明格式不符");
            String[] fields=value.trim().split(" ");x=Integer.parseInt(fields[1]);y=Integer.parseInt(fields[2]);width=Integer.parseInt(fields[3]);height=Integer.parseInt(fields[4]);
            if (x<0 || y<0 || width<1 || height<1 || x+width>1280 || y+height>900 || !fields[6].equals(approvedFull)) throw new IllegalArgumentException("模态证明边界不符");
            dialogSha=fields[5];fullSha=fields[6];proofSha=fields[7];line=value;
        }
        String hash(byte[] raw) throws Exception { return modalHash(raw,new Rectangle(x,y,width,height)); }
    }
    static byte[] pixelPng(byte[] raw) throws Exception {
        if (raw.length>2*1024*1024 || raw.length<8 || !java.util.Arrays.equals(java.util.Arrays.copyOf(raw,8),new byte[]{(byte)137,80,78,71,13,10,26,10})) throw new IllegalArgumentException("PNG界限不符");
        var out=new ByteArrayOutputStream();out.write(raw,0,8);int at=8,count=0;boolean idat=false,end=false;
        while (at<raw.length) {
            if (++count>256 || at+12>raw.length) throw new IllegalArgumentException("PNG块界限不符");
            int n=java.nio.ByteBuffer.wrap(raw,at,4).getInt();
            if (n<0 || n>raw.length-at-12) throw new IllegalArgumentException("PNG块长度不符");
            String kind=new String(raw,at+4,4,java.nio.charset.StandardCharsets.US_ASCII);
            var crc=new java.util.zip.CRC32();crc.update(raw,at+4,n+4);
            if (crc.getValue()!=Integer.toUnsignedLong(java.nio.ByteBuffer.wrap(raw,at+8+n,4).getInt())) throw new IllegalArgumentException("PNG校验不符");
            if (kind.equals("IHDR")) {
                var b=java.nio.ByteBuffer.wrap(raw,at+8,n);
                if (count!=1 || n!=13 || b.getInt()!=1280 || b.getInt()!=900 || b.get()!=8) throw new IllegalArgumentException("PNG格式不符");
                int color=b.get();if ((color!=2 && color!=6) || b.get()!=0 || b.get()!=0 || b.get()!=0) throw new IllegalArgumentException("PNG颜色格式不符");
                out.write(raw,at,n+12);
            } else if (kind.equals("IDAT")) { idat=true;out.write(raw,at,n+12); }
            else if (kind.equals("IEND")) { if (n!=0 || !idat || at+n+12!=raw.length) throw new IllegalArgumentException("PNG结束不符");out.write(raw,at,n+12);end=true; }
            else if (raw[at+4]<'a' || raw[at+4]>'z') throw new IllegalArgumentException("未知PNG关键块");
            at+=n+12;
        }
        if (!end) throw new IllegalArgumentException("PNG不完整");return out.toByteArray();
    }
    static String modalHash(byte[] raw,Rectangle rectangle) throws Exception {
        if (rectangle.x<0 || rectangle.y<0 || rectangle.width<1 || rectangle.height<1 || rectangle.x+rectangle.width>1280 || rectangle.y+rectangle.height>900) throw new IllegalArgumentException("模态区域越界");
        var image=ImageIO.read(new java.io.ByteArrayInputStream(pixelPng(raw)));
        if (image==null || image.getWidth()!=1280 || image.getHeight()!=900) throw new IllegalArgumentException("PNG像素不符");
        var hash=MessageDigest.getInstance("SHA-256");hash.update("ACADEMY_OWNED_PLUGIN_DIALOG_RGB_V1\0".getBytes(java.nio.charset.StandardCharsets.US_ASCII));
        hash.update(java.nio.ByteBuffer.allocate(16).putInt(rectangle.x).putInt(rectangle.y).putInt(rectangle.width).putInt(rectangle.height).array());
        for(int y=0;y<900;y++) for(int x=0;x<1280;x++) {
            int value=image.getRGB(x,y);if ((value>>>24)!=255) throw new IllegalArgumentException("PNG透明像素不符");
            if(rectangle.contains(x,y)) { hash.update((byte)(value>>>16));hash.update((byte)(value>>>8));hash.update((byte)value); }
        }
        return HexFormat.of().formatHex(hash.digest());
    }
    static final class PluginComparisonState {
        ModalComparison approved;
        String phase="INITIAL_ONE",reason="WINDOW_PROOF_UNAVAILABLE",dispatch="NO_INPUT_DISPATCHED";
        byte[] frame;
        String currentDialog,currentProof;
        void compare(byte[] current) throws Exception {
            frame=current;currentDialog=approved.hash(current);reason="MODAL_PIXELS_CHANGED";
            if (!currentDialog.equals(approved.dialogSha)) throw new IllegalStateException("完整插件协议弹窗像素变化");
            frame=null;currentDialog=null;reason="OWNERSHIP_OR_ACTION_UNAVAILABLE";
        }
        void probe(String[] args) throws Exception {
            reason="WINDOW_PROOF_UNAVAILABLE";currentProof=null;
            ModalComparison current=new ModalComparison(verifyTrustWindow(args,true),args[2]);
            if (approved!=null && !approved.line.equals(current.line)) throw new IllegalStateException("模态批准证明变化");
            approved=current;currentProof=current.proofSha;reason="OWNERSHIP_OR_ACTION_UNAVAILABLE";
        }
        void failure(String[] args,Path binding,Exception error) {
            String retained="UNAVAILABLE";
            if (error instanceof InterruptedException) reason="CANCELLED";
            try {
                if (frame!=null) { verifyOwned(binding);pixelPng(frame);privateWrite(Path.of(args[1]).resolveSibling("comparison-failure-private.png"),frame);retained="RETAINED_PRIVATE_ONLY"; }
            } catch (Exception ignored) { /* Never substitute another image or publish this private frame. */ }
            try {
                String currentFull=frame==null?null:sha(frame);
                String record="{\"schema\":1,\"action\":"+quoted(args[0])+",\"phase\":"+quoted(phase)+",\"reason\":"+quoted(reason)+",\"dispatch_state\":"+quoted(dispatch)
                    +",\"approved_full_sha256\":"+quoted(args[2])+",\"approved_dialog_sha256\":"+quoted(approved==null?null:approved.dialogSha)+",\"approved_proof_sha256\":"+quoted(approved==null?null:approved.proofSha)
                    +",\"current_full_sha256\":"+quoted(currentFull)+",\"current_dialog_sha256\":"+quoted(currentDialog)+",\"current_proof_sha256\":"+quoted(currentProof)+",\"private_frame_status\":"+quoted(retained)+"}\n";
                privateWrite(Path.of(args[1]).resolveSibling("comparison-failure.json"),record.getBytes(java.nio.charset.StandardCharsets.US_ASCII));
            } catch (Exception ignored) { /* Optional diagnostics never replace the original failure or grant input. */ }
        }
    }
    static void pluginInitialComparisons(PluginComparisonState state,CheckedStep probe,CheckedStep ownership,Snapshot image) throws Exception {
        probe.run();ownership.run();state.phase="INITIAL_ONE";state.compare(image.read());state.phase="INITIAL_TWO";state.compare(image.read());
    }
    static void pluginFinalComparison(PluginComparisonState state,CheckedStep probe,Snapshot image,CheckedStep click) throws Exception {
        state.phase="FINAL_PROBE";probe.run();state.phase="FINAL_PIXELS";state.compare(image.read());state.phase="PRE_PRESS";click.run();
    }
    static String quoted(String value) { return value==null?"null":"\""+value+"\""; }
    static void privateWrite(Path path,byte[] raw) throws Exception {
        Path parent=path.getParent();
        for(Path p=parent;p!=null;p=p.getParent()) if(Files.isSymbolicLink(p)) throw new IllegalStateException("诊断目录不符");
        Path tmp=Files.createTempFile(parent,".comparison-",".pending",java.nio.file.attribute.PosixFilePermissions.asFileAttribute(java.nio.file.attribute.PosixFilePermissions.fromString("rw-------")));
        try { Files.write(tmp,raw);Files.createLink(path,tmp); } finally { Files.deleteIfExists(tmp); }
    }
    private static String verifyTrustWindow(String[] args,boolean plugin) throws Exception {
        // A fixed read-only companion checks only the current owned-display window.
        // The path/arguments are generated locally, never taken from a control record.
        Process probe = new ProcessBuilder(args[4], args[5], "verify-window", "--expected", args[6], "--root", args[7])
            .redirectOutput(plugin ? ProcessBuilder.Redirect.PIPE : ProcessBuilder.Redirect.DISCARD).redirectError(ProcessBuilder.Redirect.DISCARD).start();
        try {
            if (!probe.waitFor(plugin ? 2 : 3, TimeUnit.SECONDS) || probe.exitValue()!=0) throw new IllegalStateException("窗口或本次信任绑定变化");
            if (!plugin) return "";
            byte[] raw=probe.getInputStream().readNBytes(301);if(raw.length>300 || probe.getInputStream().read()!=-1) throw new IllegalStateException("模态证明输出过大");
            return new String(raw,java.nio.charset.StandardCharsets.US_ASCII);
        } finally {
            // This handle is solely the directly spawned read-only probe, never a PID lookup.
            if (probe.isAlive()) { probe.destroyForcibly(); probe.waitFor(1, TimeUnit.SECONDS); }
        }
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 3 && args.length != 5 && args.length != 9 && args.length != 11) throw new IllegalArgumentException("参数数量不符");
        Path binding=Path.of(args[args.length-1]);
        verifyOwned(binding);
        var device = GraphicsEnvironment.getLocalGraphicsEnvironment().getDefaultScreenDevice();
        var bounds = device.getDefaultConfiguration().getBounds();
        if (!bounds.equals(new Rectangle(0, 0, 1280, 900))) throw new IllegalStateException("显示器尺寸不符");
        var robot = new Robot(device);
        if (args[0].equals("SNAPSHOT") && args.length == 3) {
            byte[] data=capture(robot,bounds);verifyOwned(binding);
            Files.write(Path.of(args[1]),data,StandardOpenOption.CREATE_NEW);
            return;
        }
        boolean trust=args[0].equals("TRUST_VALIDATION_PROJECT");
        boolean plugin=args[0].equals("CHECK_ACADEMY_PLUGIN_ONLY") || args[0].equals("AGREE_ACADEMY_PLUGIN_ONLY");
        boolean profile=args[0].equals("ENABLE_BROWSER_OPTIONS") || args[0].equals("INSTALL_SCOPED_APPARMOR_PROFILE");
        boolean install=args[0].equals("INSTALL_SCOPED_APPARMOR_PROFILE");
        boolean terminal=args[0].equals("ACK_VENDOR_INSTALL_COMPLETION");
        boolean bound=trust || plugin || profile || terminal;
        if (args.length != (profile ? 11 : bound ? 9 : 5) || !args[2].matches("[0-9a-f]{64}")) throw new IllegalArgumentException("截图摘要不符");
        // 固定 SDK、1280x900 无窗口管理器的已观察布局；审图人员须确认目标点确在相应控件内。
        int x, y;
        switch(args[0]) {
            case "CHECK_EUA": x=382; y=612; break;
            case "CONTINUE_EUA": x=879; y=651; break;
            case "DECLINE_USAGE": x=663; y=651; break;
            case "TRUST_VALIDATION_PROJECT": x=596; y=517; break;
            case "CHECK_ACADEMY_PLUGIN_ONLY": x=448; y=403; break;
            case "AGREE_ACADEMY_PLUGIN_ONLY": x=765; y=539; break;
            case "ACK_VENDOR_INSTALL_COMPLETION": x=-1; y=-1; break; // No click, focus change, or text input.
            case "ENABLE_BROWSER_OPTIONS":
            case "INSTALL_SCOPED_APPARMOR_PROFILE":
                int[] point=profilePoint(args[8],args[9]);x=point[0];y=point[1];
                break;
            default: throw new IllegalArgumentException("不支持的动作");
        }
        PluginComparisonState modal=plugin ? new PluginComparisonState() : null;
        try {
            if (plugin) pluginInitialComparisons(modal,()->modal.probe(args),()->verifyOwned(binding),()->capture(robot,bounds));
            else {
                if (!sha(capture(robot,bounds)).equals(args[2])) throw new IllegalStateException("当前画面与批准画面不同");
                if (!sha(capture(robot,bounds)).equals(args[2])) throw new IllegalStateException("再次采集画面不同");
            }
            verifyOwned(binding);
            CheckedStep click = () -> {
                if (plugin) { modal.dispatch="DISPATCH_STARTED";modal.phase="POST_PRESS"; }
                if (terminal) { robot.keyPress(KeyEvent.VK_ENTER); robot.keyRelease(KeyEvent.VK_ENTER); }
                else { robot.mousePress(InputEvent.BUTTON1_DOWN_MASK); robot.mouseRelease(InputEvent.BUTTON1_DOWN_MASK); }
            };
            if (plugin) {
                pluginFinalComparison(modal,()->{modal.probe(args);modal.probe(args);verifyOwned(binding);},()->capture(robot,bounds),()->{
                    // No blocking companion after the exact complete-dialog comparison.
                    robot.mouseMove(x,y);
                    profileClick(() -> verifyOwned(binding), () -> {
                        if (Files.exists(Path.of(args[7]).resolve("cancelled.json"))) throw new InterruptedException("本次准备已取消");
                    },click);
                });
            } else if (bound) {
                verifyTrustWindow(args,false);
                finalTrustClick(() -> { verifyTrustWindow(args,false); verifyOwned(binding); },
                    () -> capture(robot,bounds),args[2],() -> {
                        if (!terminal) robot.mouseMove(x,y);
                        if (profile || terminal) profileClick(() -> verifyOwned(binding), () -> {
                            if (Files.exists(Path.of(args[7]).resolve("cancelled.json"))) throw new InterruptedException("本次准备已取消");
                        },click);
                        else { verifyOwned(binding);click.run(); }
                    });
            } else { robot.mouseMove(x,y); verifyOwned(binding); click.run(); }
        if (install || terminal) {
            // The armed normal vendor action may close this IDE immediately.
            // Record only dispatch. New process/context/images prove outcome.
            Files.writeString(Path.of(args[3]),args[0]+"\n",StandardOpenOption.CREATE_NEW);
            return;
        }
        robot.delay(500);
        verifyOwned(binding);
        Files.write(Path.of(args[1]),capture(robot,bounds),StandardOpenOption.CREATE_NEW);
        Files.writeString(Path.of(args[3]),args[0]+"\n",StandardOpenOption.CREATE_NEW);
        } catch (Exception error) { if(plugin) modal.failure(args,binding,error);throw error; }
    }
}
