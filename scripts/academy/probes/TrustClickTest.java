import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.ArrayList;
import java.util.List;

/** Pure callbacks, no Robot/window/native process/course/trust action. */
class TrustClickTest {
    static int tests;
    static String sha(byte[] value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
    }
    static void require(boolean value) { if (!value) throw new AssertionError(); }
    public static void main(String[] args) throws Exception {
        byte[] approved="synthetic unchecked dialog".getBytes();
        byte[][] current={approved};int[] clicks={0};List<String> order=new ArrayList<>();
        AgreementUi.finalTrustClick(() -> order.add("probe"), () -> { order.add("image"); return current[0]; },
                                    sha(approved), () -> { order.add("click"); clicks[0]++; });
        require(clicks[0]==1 && order.equals(List.of("probe","image","click")));tests++;
        for (String changed : List.of("synthetic checked parent checkbox","synthetic different project dialog","synthetic AI checkbox selected","synthetic base plugin checkbox changed","synthetic Disable Sandbox option","synthetic different profile destination","synthetic terminal password prompt","synthetic terminal focus changed")) {
            clicks[0]=0;current[0]=approved;
            try {
                AgreementUi.finalTrustClick(() -> current[0]=changed.getBytes(), () -> current[0],sha(approved), () -> clicks[0]++);
                throw new AssertionError("changed pixels accepted");
            } catch (IllegalStateException expected) { require(clicks[0]==0); }
            tests++;
        }
        clicks[0]=0;order.clear();
        try {
            AgreementUi.finalTrustClick(() -> { throw new InterruptedException("synthetic cancellation"); },
                () -> { order.add("image"); return approved; },sha(approved), () -> clicks[0]++);
            throw new AssertionError("cancellation swallowed");
        } catch (InterruptedException expected) { require(clicks[0]==0 && order.isEmpty()); }
        tests++;
        order.clear();clicks[0]=0;
        try {
            AgreementUi.profileClick(() -> order.add("identity"), () -> { order.add("cancel");throw new InterruptedException("latched"); }, () -> clicks[0]++);
            throw new AssertionError("profile cancellation ignored");
        } catch (InterruptedException expected) {require(clicks[0]==0 && order.equals(List.of("identity","cancel")));}
        tests++;
        order.clear();clicks[0]=0;
        AgreementUi.finalTrustClick(() -> order.add("focused-terminal-probe"), () -> { order.add("image");return approved; },sha(approved),
            () -> AgreementUi.profileClick(() -> order.add("identity"), () -> order.add("cancel"), () -> {order.add("ENTER");clicks[0]++;}));
        require(clicks[0]==1 && order.equals(List.of("focused-terminal-probe","image","identity","cancel","ENTER")));tests++;
        for (String[] point : List.of(new String[]{"1280","1"},new String[]{"1","900"},new String[]{"-1","1"},new String[]{"true","1"})) {
            try {AgreementUi.profilePoint(point[0],point[1]);throw new AssertionError("bad point accepted");}
            catch (IllegalArgumentException expected) { tests++; }
        }
        System.out.println("PASS: "+tests+" synthetic final-probe/image/click cases; NO_GUI_ACTION");
    }
}
