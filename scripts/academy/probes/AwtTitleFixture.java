import java.awt.EventQueue;
import java.awt.Frame;
import java.awt.Toolkit;

/** Ordinary AWT titles only; no IDE, settings, dialogs, or input dispatch. */
public final class AwtTitleFixture {
    private static final String RUNTIME = "25.0.4+1-b329.128";
    private static final String[] TITLES = {
        "Academy AWT title fixture ASCII",
        "Academy AWT title fixture \u4e2d\u6587\u6807\u9898"
    };

    public static void main(String[] args) throws Exception {
        if (args.length != 0 || !RUNTIME.equals(System.getProperty("java.runtime.version"))) {
            System.exit(2);
        }
        Frame[] frames = new Frame[TITLES.length];
        EventQueue.invokeAndWait(() -> {
            for (int i = 0; i < TITLES.length; i++) {
                Frame frame = new Frame(TITLES[i]);
                frame.setBounds(100 + 360 * i, 100, 320, 160);
                frame.setVisible(true);
                frames[i] = frame;
            }
            Toolkit.getDefaultToolkit().sync();
        });
        System.out.print("AWT_TITLE_FIXTURE_READY:" + RUNTIME + "\n");
        System.out.flush();
        // The coordinator owns stdin and the JVM lifetime. EOF also exits cleanly.
        try {
            while (System.in.read() != -1) { }
        } finally {
            EventQueue.invokeAndWait(() -> {
                for (Frame frame : frames) {
                    if (frame != null) frame.dispose();
                }
            });
        }
    }
}
