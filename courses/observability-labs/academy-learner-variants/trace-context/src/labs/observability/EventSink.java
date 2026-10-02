package labs.observability;
import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.file.StandardOpenOption;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.ArrayDeque;

/** Dedicated business JSON file; framework console logs are not ingested as these events. */
public final class EventSink {
    private final Path path;
    private final ArrayDeque<String> recent = new ArrayDeque<>();
    private long writeFailures;
    public EventSink(Path path) { this.path=path; }
    public synchronized void accept(String line) {
        if (recent.size()==256) recent.removeFirst();
        recent.addLast(line);
        if (path!=null) try {
            if (path.getParent()!=null) Files.createDirectories(path.getParent());
            Files.writeString(path,line+"\n",StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        } catch(IOException failure) { writeFailures++; System.err.println("telemetry.event_write_failed count="+writeFailures); }
    }
    public synchronized List<String> recent() { return List.copyOf(recent); }
    public synchronized long writeFailures() { return writeFailures; }
}
