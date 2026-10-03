package labs.identity;
import static org.junit.jupiter.api.Assertions.*;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** 公开业务合同v2：11个顶层方法，matrix方法内144组，数量分开报告。 */
class PolicyTest {
    private static Policy.Subject subject(String id,String tenant,Set<String> roles,boolean authenticated) {
        return new Policy.Subject(id,tenant,roles,authenticated);
    }
    private static Policy.Subject reader() { return subject("fixture-alice","tenant-a",Set.of("reader"),true); }
    private static Policy.Resource own() { return new Policy.Resource("order-a","tenant-a"); }
    private static void expect(Policy.Subject s,String action,Policy.Resource r,boolean allowed,String reason) {
        assertEquals(new Policy.Decision(allowed,reason),Policy.authorize(s,action,r),
            "C15-POLICY: allowed与固定reason必须共同满足合同");
    }
    @Test void policyMatrixContract() {
        List<Set<String>> roles=List.of(Set.of(),Set.of("reader"),Set.of("editor"),Set.of("admin"),Set.of("unknown"),Set.of("reader","unknown"));
        int count=0;
        for(var role:roles) for(String action:List.of("order:read","order:approve","user:delete",""))
            for(String tenant:List.of("tenant-a","tenant-b","")) for(boolean auth:List.of(true,false)) {
                boolean permission=action.equals("order:read")
                    ? role.contains("reader")||role.contains("editor")||role.contains("admin")
                    : action.equals("order:approve")&&(role.contains("editor")||role.contains("admin"));
                String reason=!auth?"UNAUTHENTICATED":tenant.isEmpty()?"MISSING_ATTRIBUTE":
                    !tenant.equals("tenant-a")?"TENANT_MISMATCH":
                    !Set.of("order:read","order:approve").contains(action)?"UNKNOWN_ACTION":
                    permission?"ALLOW":"ROLE_DENIED";
                expect(subject("fixture",tenant,role,auth),action,own(),reason.equals("ALLOW"),reason);
                count++;
            }
        assertEquals(144,count,"矩阵用例不能静默减少");
    }
    @Test void unauthenticatedInputs() {
        expect(null,null,null,false,"UNAUTHENTICATED");
        expect(subject("fixture","tenant-a",Set.of("admin"),false),"order:read",own(),false,"UNAUTHENTICATED");
    }
    @Test void invalidSubjectId() {
        for(String id:new String[]{null,""," ","\t\n"})
            expect(subject(id,"tenant-a",Set.of("admin"),true),"order:read",own(),false,"UNAUTHENTICATED");
    }
    @Test void missingResource() { expect(reader(),"order:read",null,false,"MISSING_ATTRIBUTE"); }
    @Test void invalidResourceId() {
        for(String id:new String[]{null,""," ","\t"})
            expect(reader(),"order:read",new Policy.Resource(id,"tenant-a"),false,"MISSING_ATTRIBUTE");
    }
    @Test void invalidSubjectTenant() {
        for(String tenant:new String[]{null,""," ","\t"})
            expect(subject("fixture",tenant,Set.of("admin"),true),"order:read",own(),false,"MISSING_ATTRIBUTE");
    }
    @Test void invalidResourceTenant() {
        for(String tenant:new String[]{null,""," ","\t"})
            expect(reader(),"order:read",new Policy.Resource("a",tenant),false,"MISSING_ATTRIBUTE");
    }
    @Test void denialPrecedence() {
        expect(subject("",null,Set.of(),false),null,null,false,"UNAUTHENTICATED");
        expect(subject("fixture","",Set.of("admin"),true),"unknown",new Policy.Resource("b","tenant-b"),false,"MISSING_ATTRIBUTE");
        expect(subject("fixture","tenant-b",Set.of("admin"),true),null,own(),false,"TENANT_MISMATCH");
        expect(subject("fixture","tenant-a",Set.of(),true),null,own(),false,"UNKNOWN_ACTION");
        expect(subject("fixture","tenant-a",Set.of(),true),"order:read",own(),false,"ROLE_DENIED");
    }
    @Test void fixedDecisionReasons() {
        expect(reader(),"order:read",own(),true,"ALLOW");
        expect(reader(),"order:approve",own(),false,"ROLE_DENIED");
        expect(reader(),"order:read",new Policy.Resource("b","tenant-b"),false,"TENANT_MISMATCH");
        expect(reader(),"user:delete",own(),false,"UNKNOWN_ACTION");
        expect(subject("fixture","tenant-a",Set.of("editor"),true),"order:approve",own(),true,"ALLOW");
    }
    @Test void rolesAreEmptyOrImmutable() {
        expect(subject("fixture","tenant-a",null,true),"order:read",own(),false,"ROLE_DENIED");
        var incoming=new HashSet<String>();incoming.add("reader");
        var s=subject("fixture","tenant-a",incoming,true);incoming.add("admin");
        expect(s,"order:approve",own(),false,"ROLE_DENIED");
        assertThrows(UnsupportedOperationException.class,()->s.roles().add("admin"));
    }
    @Test void unknownActionsFailClosed() {
        for(String action:new String[]{null,""," ","order:delete"})
            expect(subject("fixture","tenant-a",Set.of("admin"),true),action,own(),false,"UNKNOWN_ACTION");
        expect(subject("fixture","tenant-a",Set.of("root"),true),"order:read",own(),false,"ROLE_DENIED");
    }
}
