package lab

import (
	"context"
	"errors"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
)

func TestGinPipeline(t *testing.T) {
	t.Run("unauthorized_stops_chain", func(t *testing.T) {
		calls := 0
		h := NewHandler(StoreFunc(func(context.Context, Input) (Order, error) { calls++; return Order{}, nil }), time.Second)
		r := request("POST", orderPath, validJSON)
		r.Header.Del("X-Lab-Key")
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, r)
		assertResponse(t, rr, 401, "demo_key_required")
		if calls != 0 {
			t.Fatal("GIN_ABORT service ran after gate rejected")
		}
	})
	t.Run("next_unwinds", func(t *testing.T) {
		var order []string
		r := gin.New()
		r.Use(ErrorEnvelope())
		r.Use(func(c *gin.Context) {
			order = append(order, "outer_before")
			c.Next()
			order = append(order, "outer_after")
		})
		r.GET("/ok", RequireDemoKey(), func(c *gin.Context) { order = append(order, "handler"); c.JSON(200, gin.H{"ok": true}) })
		rr := httptest.NewRecorder()
		r.ServeHTTP(rr, request("GET", "/ok", ""))
		assertResponse(t, rr, 200, "")
		if !reflect.DeepEqual(order, []string{"outer_before", "handler", "outer_after"}) {
			t.Fatalf("GIN_NEXT order=%v", order)
		}
	})
	t.Run("unknown_error_redacted", func(t *testing.T) {
		r := gin.New()
		r.Use(ErrorEnvelope())
		r.GET("/error", func(c *gin.Context) { _ = c.Error(errors.New("secret database address")) })
		rr := httptest.NewRecorder()
		r.ServeHTTP(rr, request("GET", "/error", ""))
		assertResponse(t, rr, 500, "internal_error")
		if strings.Contains(rr.Body.String(), "secret") {
			t.Fatal("GIN_LEAK raw errors exposed")
		}
	})
	t.Run("committed_response_not_overwritten", func(t *testing.T) {
		r := gin.New()
		r.Use(ErrorEnvelope())
		r.GET("/written", func(c *gin.Context) { c.JSON(202, gin.H{"accepted": true}); _ = c.Error(errors.New("late error")) })
		rr := httptest.NewRecorder()
		r.ServeHTTP(rr, request("GET", "/written", ""))
		if rr.Code != 202 || rr.Body.String() != `{"accepted":true}` {
			t.Fatalf("GIN_DOUBLE_WRITE %d %s", rr.Code, rr.Body.String())
		}
	})
	t.Run("panic_sanitized", func(t *testing.T) {
		r := NewHandler(StoreFunc(func(context.Context, Input) (Order, error) { panic("private panic detail") }), time.Second)
		rr := httptest.NewRecorder()
		r.ServeHTTP(rr, request("POST", orderPath, validJSON))
		assertResponse(t, rr, 500, "internal_error")
		if strings.Contains(rr.Body.String(), "private") {
			t.Fatal("GIN_PANIC leak")
		}
	})
	t.Run("health_is_public", func(t *testing.T) {
		r := NewHandler(&MemoryStore{}, time.Second)
		req := request("GET", "/healthz", "")
		req.Header.Del("X-Lab-Key")
		rr := httptest.NewRecorder()
		r.ServeHTTP(rr, req)
		assertResponse(t, rr, 200, "")
	})
}
