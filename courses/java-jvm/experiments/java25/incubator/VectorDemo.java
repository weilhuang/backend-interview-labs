import jdk.incubator.vector.IntVector;

public class VectorDemo {
    public static void main(String[] args) {
        var value = IntVector.broadcast(IntVector.SPECIES_128, 3);
        System.out.println(value.lane(0));
    }
}
