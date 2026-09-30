package labs.foundation;

public final class ParseFailure extends IllegalArgumentException {
    private final int line;
    private final String field;

    public ParseFailure(int line, String field, String reason) {
        super("第" + line + "行，字段" + field + "：" + reason);
        this.line = line;
        this.field = field;
    }

    public int line() {
        return line;
    }

    public String field() {
        return field;
    }
}
