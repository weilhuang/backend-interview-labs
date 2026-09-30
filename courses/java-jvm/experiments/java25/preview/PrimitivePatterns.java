public class PrimitivePatterns {
    public static void main(String[] args) {
        Object value = Integer.valueOf(7);
        String text = switch (value) {
            case int n -> "整数=" + n;
            default -> "其他";
        };
        System.out.println(text);
    }
}
