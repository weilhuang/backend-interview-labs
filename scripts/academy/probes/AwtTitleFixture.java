import java.awt.EventQueue;
import java.awt.Frame;
import java.awt.Dialog;
import java.awt.Toolkit;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JDialog;
import javax.swing.JLabel;
import javax.swing.JPanel;

/** Genuine private AWT/Swing peers; no IDE, legal text, or input dispatch. */
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
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(40);
        CountDownLatch showing = new CountDownLatch(1);
        CountDownLatch eof = new CountDownLatch(1);
        AtomicBoolean announced = new AtomicBoolean();
        Frame[] frames = new Frame[TITLES.length];
        JDialog[] dialogs = new JDialog[1];
        EventQueue.invokeAndWait(() -> {
            for (int i = 0; i < TITLES.length; i++) {
                Frame frame = new Frame(TITLES[i]);
                frame.setBounds(100 + 360 * i, 100, 320, 160);
                frame.setVisible(true);
                frames[i] = frame;
            }
            JDialog dialog = new JDialog(frames[0], "Academy AWT modal fixture",
                                        Dialog.ModalityType.APPLICATION_MODAL);
            dialog.setUndecorated(true);
            dialog.setDefaultCloseOperation(JDialog.DO_NOTHING_ON_CLOSE);
            dialog.setBounds(380, 335, 520, 235);
            JPanel content = new JPanel(null);
            JLabel label = new JLabel("Private window proof fixture");
            label.setBounds(24, 12, 450, 28);
            JCheckBox first = new JCheckBox("Synthetic option one");
            first.setBounds(48, 48, 340, 40);
            JCheckBox second = new JCheckBox("Synthetic option two");
            second.setBounds(48, 100, 340, 40);
            JButton button = new JButton("Fixture button");
            button.setBounds(318, 182, 150, 42);
            content.add(label);
            content.add(first);
            content.add(second);
            content.add(button);
            dialog.setContentPane(content);
            dialog.addWindowListener(new WindowAdapter() {
                @Override public void windowOpened(WindowEvent event) {
                    if (dialog.isShowing() && announced.compareAndSet(false, true)) {
                        dialog.requestFocus();
                        first.requestFocusInWindow();
                        Toolkit.getDefaultToolkit().sync();
                        System.out.print("AWT_TITLE_FIXTURE_READY:" + RUNTIME + "\n");
                        System.out.flush();
                        showing.countDown();
                    }
                }
            });
            dialogs[0] = dialog;
            Toolkit.getDefaultToolkit().sync();
        });
        // A modal show runs a nested event loop. Never wait for it in invokeAndWait.
        EventQueue.invokeLater(() -> dialogs[0].setVisible(true));
        Thread input = new Thread(() -> {
            try {
                while (System.in.read() != -1) { }
            } catch (java.io.IOException ignored) {
                // An unavailable coordinator pipe ends this private fixture too.
            } finally {
                eof.countDown();
            }
        }, "fixture-coordinator-eof");
        input.setDaemon(true);
        input.start();
        // READY only means showing. The unchanged production probe proves focus.
        // Both waits use the original deadline; stdin cannot extend the lifecycle.
        try {
            if (!showing.await(Math.max(0, Math.min(TimeUnit.SECONDS.toNanos(20),
                    deadline - System.nanoTime())), TimeUnit.NANOSECONDS)) {
                throw new IllegalStateException("FIXTURE_NOT_SHOWING");
            }
            eof.await(Math.max(0, deadline - System.nanoTime()), TimeUnit.NANOSECONDS);
        } finally {
            EventQueue.invokeLater(() -> {
                if (dialogs[0] != null) dialogs[0].dispose();
                for (Frame frame : frames) {
                    if (frame != null) frame.dispose();
                }
            });
        }
    }
}
