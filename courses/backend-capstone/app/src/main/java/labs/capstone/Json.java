package labs.capstone;

import com.fasterxml.jackson.databind.ObjectMapper;

public final class Json {
    public static final ObjectMapper MAPPER = new ObjectMapper();

    private Json() {}

    public static String write(Object value) {
        try {
            return MAPPER.writeValueAsString(value);
        } catch (Exception failure) {
            throw new IllegalArgumentException("不能编码课堂数据", failure);
        }
    }

    public static <T> T read(String value, Class<T> type) {
        try {
            return MAPPER.readValue(value, type);
        } catch (Exception failure) {
            throw new IllegalArgumentException("不能解析课堂数据", failure);
        }
    }
}
