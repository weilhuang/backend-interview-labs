package labs.capstone;

import io.grpc.*;

import labs.capstone.protocol.*;

import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

/** 容器就绪探针只读，不发布消息、不改业务数据。 */
public final class HealthMain {
    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("rpc")) {
            Config c = Config.environment();
            ManagedChannel ch =
                    ManagedChannelBuilder.forAddress("127.0.0.1", c.rpcPort())
                            .usePlaintext()
                            .build();
            try {
                if (!DeliveryGrpc.newBlockingStub(ch)
                        .withDeadlineAfter(2, TimeUnit.SECONDS)
                        .probe(ProbeRequest.getDefaultInstance())
                        .getStatus()
                        .equals("READY")) throw new IllegalStateException("RPC未就绪");
            } finally {
                ch.shutdownNow();
                ch.awaitTermination(2, TimeUnit.SECONDS);
            }
        } else {
            var response =
                    HttpClient.newBuilder()
                            .connectTimeout(Duration.ofSeconds(2))
                            .build()
                            .send(
                                    HttpRequest.newBuilder(
                                                    URI.create("http://127.0.0.1:8080/api/ready"))
                                            .timeout(Duration.ofSeconds(3))
                                            .GET()
                                            .build(),
                                    HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) throw new IllegalStateException("HTTP尚未就绪");
        }
    }
}
