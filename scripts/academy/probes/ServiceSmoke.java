package lab.environment;
import java.sql.DriverManager;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;

/** External loopback protocol probes; dependencies come from the imported course's strict lock. */
public final class ServiceSmoke {
 public static void main(String[] args) throws Exception {
  if(args.length!=4 || !"true".equals(System.getenv("CI")) || !args[3].matches("totalacademy-ci-\\d+-\\d+"))throw new IllegalArgumentException("CI-only probe");
  if(Runtime.version().feature()!=21)throw new IllegalStateException("JDK21 required");
  var action=args[0];var endpoint=args[1];var database=args[2];var marker=args[3];
  if(!endpoint.matches("127\\.0\\.0\\.1:[1-9][0-9]{3,4}"))throw new IllegalArgumentException("loopback endpoint required");
  if(action.startsWith("mysql-")){
   try(var connection=DriverManager.getConnection("jdbc:mysql://"+endpoint+"/"+database+"?connectTimeout=10000&socketTimeout=15000",System.getenv("MYSQL_USER"),System.getenv("MYSQL_PASSWORD"))){
    if(action.equals("mysql-write")){
     try(var statement=connection.createStatement()){statement.execute("CREATE TABLE academy_ci (id INT PRIMARY KEY, marker VARCHAR(120) NOT NULL)");}
     try(var statement=connection.prepareStatement("INSERT INTO academy_ci VALUES (1,?)")){statement.setString(1,marker);if(statement.executeUpdate()!=1)throw new AssertionError("insert count");}
    } else if(!action.equals("mysql-read"))throw new IllegalArgumentException("action");
    try(var statement=connection.createStatement();var result=statement.executeQuery("SELECT marker FROM academy_ci WHERE id=1")){
     if(!result.next() || !marker.equals(result.getString(1)) || result.next())throw new AssertionError("MySQL roundtrip/persistence mismatch");
    }
   }
  } else if(action.startsWith("kafka-")){
   var topic="academy-ci";
   if(action.equals("kafka-write")){
    try(var admin=AdminClient.create(Map.of("bootstrap.servers",endpoint,"request.timeout.ms",10000,"default.api.timeout.ms",30000))){
     admin.createTopics(List.of(new NewTopic(topic,1,(short)1))).all().get(30,TimeUnit.SECONDS);
    }
    Properties properties=new Properties();properties.put("bootstrap.servers",endpoint);properties.put("acks","all");properties.put("key.serializer","org.apache.kafka.common.serialization.StringSerializer");properties.put("value.serializer","org.apache.kafka.common.serialization.StringSerializer");properties.put("max.block.ms","30000");properties.put("delivery.timeout.ms","30000");properties.put("request.timeout.ms","10000");
    try(var producer=new KafkaProducer<String,String>(properties)){producer.send(new ProducerRecord<>(topic,marker,marker)).get(35,TimeUnit.SECONDS);}
   }else if(!action.equals("kafka-read"))throw new IllegalArgumentException("action");
   Properties properties=new Properties();properties.put("bootstrap.servers",endpoint);properties.put("group.id",marker+"-"+action);properties.put("auto.offset.reset","earliest");properties.put("enable.auto.commit","false");properties.put("key.deserializer","org.apache.kafka.common.serialization.StringDeserializer");properties.put("value.deserializer","org.apache.kafka.common.serialization.StringDeserializer");properties.put("request.timeout.ms","10000");properties.put("default.api.timeout.ms","30000");
   boolean found=false;
   try(var consumer=new KafkaConsumer<String,String>(properties)){
    consumer.subscribe(List.of(topic));long deadline=System.nanoTime()+Duration.ofSeconds(40).toNanos();
    while(!found && System.nanoTime()<deadline){for(var record:consumer.poll(Duration.ofSeconds(2))){if(!marker.equals(record.key()) || !marker.equals(record.value()))throw new AssertionError("Kafka payload mismatch");found=true;}}
   }
   if(!found)throw new AssertionError("Kafka message missing");
  }else throw new IllegalArgumentException("unknown action");
  System.out.println("SERVICE_SMOKE_OK="+action);
 }
}
