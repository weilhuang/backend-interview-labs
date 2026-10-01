import java.awt.GraphicsEnvironment;
import java.awt.Rectangle;
import java.awt.Robot;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import javax.imageio.ImageIO;

/** 只读取本次专用 Xvfb 的固定画面；不发送鼠标、键盘或窗口事件。 */
class StartupScreen {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("必须指定新截图文件");
        var device = GraphicsEnvironment.getLocalGraphicsEnvironment().getDefaultScreenDevice();
        var bounds = device.getDefaultConfiguration().getBounds();
        if (!bounds.equals(new Rectangle(0, 0, 1280, 900))) {
            throw new IllegalStateException("专用显示器尺寸与诊断约定不符");
        }
        var screenshot = new Robot(device).createScreenCapture(bounds);
        try (OutputStream stream = Files.newOutputStream(Path.of(args[0]),
                StandardOpenOption.WRITE, StandardOpenOption.CREATE_NEW)) {
            if (!ImageIO.write(screenshot, "png", stream)) {
                throw new IllegalStateException("PNG 编码器不可用");
            }
        }
    }
}
