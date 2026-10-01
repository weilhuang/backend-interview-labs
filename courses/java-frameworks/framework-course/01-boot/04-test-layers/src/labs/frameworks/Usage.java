package labs.frameworks;

public class Usage {
  public static void main(String[] args) {
    var q = new Lab.Quotes(() -> 150);
    System.out.println("两件商品报价：" + q.total(2) + "分");
  }
}
