import java.awt.GraphicsEnvironment;
import java.awt.Rectangle;
import java.awt.Robot;
import java.awt.event.InputEvent;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Properties;
import java.util.concurrent.TimeUnit;
import javax.imageio.ImageIO;

/** 仅供本次专用 Xvfb；动作不接受坐标、文本或任意命令。 */
class AgreementUi {
    interface CheckedStep { void run() throws Exception; }
    interface Snapshot { byte[] read() throws Exception; }
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
        for (String kind : new String[]{"wrapper", "server", "ide"}) {
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
    private static void verifyTrustWindow(String[] args) throws Exception {
        // A fixed read-only companion checks only the current owned-display window.
        // The path/arguments are generated locally, never taken from a control record.
        Process probe = new ProcessBuilder(args[4], args[5], "verify-window", "--expected", args[6], "--root", args[7])
            .redirectOutput(ProcessBuilder.Redirect.DISCARD).redirectError(ProcessBuilder.Redirect.DISCARD).start();
        try {
            if (!probe.waitFor(3, TimeUnit.SECONDS) || probe.exitValue()!=0) throw new IllegalStateException("窗口或本次信任绑定变化");
        } finally {
            // This handle is solely the directly spawned read-only probe, never a PID lookup.
            if (probe.isAlive()) { probe.destroyForcibly(); probe.waitFor(1, TimeUnit.SECONDS); }
        }
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 3 && args.length != 5 && args.length != 9) throw new IllegalArgumentException("参数数量不符");
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
        if (args.length != (trust ? 9 : 5) || !args[2].matches("[0-9a-f]{64}")) throw new IllegalArgumentException("截图摘要不符");
        // 固定 SDK、1280x900 无窗口管理器的已观察布局；审图人员须确认目标点确在相应控件内。
        int x, y;
        switch(args[0]) {
            case "CHECK_EUA": x=382; y=612; break;
            case "CONTINUE_EUA": x=879; y=651; break;
            case "DECLINE_USAGE": x=663; y=651; break;
            case "TRUST_VALIDATION_PROJECT": x=596; y=517; break;
            default: throw new IllegalArgumentException("不支持的动作");
        }
        // 同一调用中再次全图比对；任何动态变化均拒绝，不做坐标猜测或自动适配。
        if (!sha(capture(robot,bounds)).equals(args[2])) throw new IllegalStateException("当前画面与批准画面不同");
        if (!sha(capture(robot,bounds)).equals(args[2])) throw new IllegalStateException("再次采集画面不同");
        verifyOwned(binding);
        CheckedStep click = () -> {
            robot.mousePress(InputEvent.BUTTON1_DOWN_MASK);
            robot.mouseRelease(InputEvent.BUTTON1_DOWN_MASK);
        };
        if (trust) {
            verifyTrustWindow(args);
            finalTrustClick(() -> { verifyTrustWindow(args); verifyOwned(binding); },
                () -> capture(robot,bounds),args[2],() -> {
                    robot.mouseMove(x,y); verifyOwned(binding); click.run();
                });
        } else {
            robot.mouseMove(x,y); verifyOwned(binding); click.run();
        }
        robot.delay(500);
        verifyOwned(binding);
        Files.write(Path.of(args[1]),capture(robot,bounds),StandardOpenOption.CREATE_NEW);
        Files.writeString(Path.of(args[3]),args[0]+"\n",StandardOpenOption.CREATE_NEW);
    }
}
