package labs;
import java.net.*;
import java.net.http.*;
import java.time.Duration;
/** 同镜像调用方：在Pod里验证Service DNS/HTTP，不增加curl/busybox镜像。 */
public final class HttpCaller {
    public static void main(String[] args) {
        try {
            if(args.length<1 || args.length>2)throw new IllegalArgumentException();
            URI uri=URI.create(args[0]);String host=uri.getHost();
            if(!"http".equals(uri.getScheme()) || uri.getUserInfo()!=null || uri.getPort()!=8080 || host==null || !(host.equals("orders") || host.matches("orders\\.c11-kind-[a-f0-9]{12}\\.svc\\.cluster\\.local") || host.equals("127.0.0.1")))throw new IllegalArgumentException();
            var request=HttpRequest.newBuilder(uri).timeout(Duration.ofSeconds(3));
            if(args.length==2 && args[1].equals("POST"))request.POST(HttpRequest.BodyPublishers.noBody());else request.GET();
            var result=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build().send(request.build(),HttpResponse.BodyHandlers.ofString());
            System.out.println("{\"status\":"+result.statusCode()+",\"body\":"+result.body()+"}");
            System.exit(result.statusCode()<500?0:1);
        }catch(Exception e){System.err.println("{\"error\":\"CALLER_TRANSPORT\"}");System.exit(3);}
    }
}
