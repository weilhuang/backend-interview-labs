import java.awt.Rectangle;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.HexFormat;
import javax.imageio.ImageIO;

/** Pure image/callback tests. No Robot, display, IDE, agreement or input event. */
class ModalClickTest {
    static int tests;
    static void require(boolean value) {if(!value) throw new AssertionError();}
    static String sha(byte[] raw) throws Exception {return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw));}
    static byte[] image(int x,int y) throws Exception {
        var image=new BufferedImage(1280,900,BufferedImage.TYPE_INT_RGB);if(x>=0) image.setRGB(x,y,0x1234ab);
        var out=new ByteArrayOutputStream();ImageIO.write(image,"png",out);return out.toByteArray();
    }
    static AgreementUi.PluginComparisonState state(byte[] approved) throws Exception {
        var state=new AgreementUi.PluginComparisonState();
        state.approved=new AgreementUi.ModalComparison("MODAL1 380 335 520 235 "+AgreementUi.modalHash(approved,new Rectangle(380,335,520,235))+" "+sha(approved)+" "+"a".repeat(64)+"\n",sha(approved));return state;
    }
    public static void main(String[] args) throws Exception {
        byte[] approved=image(-1,0),background=image(0,0),changed=image(448,403);
        var state=state(approved);List<String> order=new ArrayList<>();int[] frames={0},clicks={0};
        AgreementUi.pluginInitialComparisons(state,()->order.add("probe-initial"),()->order.add("owned"),()->{order.add("image-"+(++frames[0]));return background;});
        AgreementUi.pluginFinalComparison(state,()->order.add("probe-final"),()->{order.add("image-"+(++frames[0]));return background;},()->{order.add("click");clicks[0]++;});
        require(frames[0]==3 && clicks[0]==1 && order.equals(List.of("probe-initial","owned","image-1","image-2","probe-final","image-3","click")));tests++;
        for(int site=1;site<=3;site++) {
            final int altered=site;var blocked=state(approved);frames[0]=0;clicks[0]=0;
            try {
                AgreementUi.pluginInitialComparisons(blocked,()->{},()->{},()->++frames[0]==altered?changed:background);
                AgreementUi.pluginFinalComparison(blocked,()->{},()->++frames[0]==altered?changed:background,()->clicks[0]++);
                throw new AssertionError("dialog change accepted");
            } catch(IllegalStateException expected) {require(clicks[0]==0 && blocked.frame==changed && blocked.dispatch.equals("NO_INPUT_DISPATCHED"));}
            tests++;
        }
        for(int[] point:new int[][]{{380,335},{899,569},{448,443},{765,539},{685,539}}) {
            try {state(approved).compare(image(point[0],point[1]));throw new AssertionError("partial dialog ignored");}catch(IllegalStateException expected){tests++;}
        }
        byte[][] current={background};clicks[0]=0;var race=state(approved);
        try {AgreementUi.pluginFinalComparison(race,()->current[0]=changed,()->current[0],()->clicks[0]++);throw new AssertionError("probe race accepted");}
        catch(IllegalStateException expected){require(clicks[0]==0);tests++;}
        order.clear();clicks[0]=0;
        try {AgreementUi.pluginFinalComparison(state(approved),()->{throw new InterruptedException();},()->{order.add("image");return background;},()->clicks[0]++);throw new AssertionError();}
        catch(InterruptedException expected){require(order.isEmpty() && clicks[0]==0);tests++;}
        try {AgreementUi.finalTrustClick(()->{},()->background,sha(approved),()->clicks[0]++);throw new AssertionError("non-plugin relaxed");}
        catch(IllegalStateException expected){require(clicks[0]==0);tests++;}
        // Dispatch marker is set before the first potentially throwing press callback.
        var dispatched=state(approved);
        try {AgreementUi.pluginFinalComparison(dispatched,()->{},()->background,()->{dispatched.dispatch="DISPATCH_STARTED";dispatched.phase="POST_PRESS";throw new IllegalStateException();});throw new AssertionError();}
        catch(IllegalStateException expected){require(dispatched.dispatch.equals("DISPATCH_STARTED") && dispatched.phase.equals("POST_PRESS"));tests++;}
        // Cancellation arriving after final pixels must still precede the first press.
        var late=state(approved);Path temporary=Files.createTempDirectory("modal-cancel-fixture-");Path latch=temporary.resolve("cancelled.json");
        order.clear();clicks[0]=0;
        try {
            AgreementUi.pluginFinalComparison(late,()->order.add("probe"),()->{order.add("final-pixels");return background;},()->{
                Files.writeString(latch,"{}");order.add("latch-after-pixels");
                AgreementUi.profileClick(()->order.add("ownership"),()->{
                    order.add("cancel-check");if(Files.exists(latch)) throw new InterruptedException("fixture-latch");
                },()->{late.dispatch="DISPATCH_STARTED";late.phase="POST_PRESS";clicks[0]++;});
            });
            throw new AssertionError("late cancellation accepted");
        } catch(InterruptedException expected) {
            require(clicks[0]==0 && late.dispatch.equals("NO_INPUT_DISPATCHED") && late.phase.equals("PRE_PRESS"));
            require(order.equals(List.of("probe","final-pixels","latch-after-pixels","ownership","cancel-check")));tests++;
        } finally {Files.deleteIfExists(latch);Files.delete(temporary);}
        if(args.length==2) {String actual=AgreementUi.modalHash(Files.readAllBytes(Path.of(args[0])),new Rectangle(380,335,520,235));require(actual.equals(args[1]));System.out.println("CROSS_LANGUAGE_RGB_SHA256="+actual);tests++;}
        System.out.println("PASS: "+tests+" modal pixel/sequencing cases; HEADLESS_NO_GUI_ACTION");
    }
}
