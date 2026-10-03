package lab

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
)

func Recovery() gin.HandlerFunc {
	return func(c *gin.Context) {
		defer func() {
			if recover() != nil {
				_ = c.Error(problem(500, "internal_error", "internal service error"))
				c.Abort()
			}
		}()
		c.Next()
	}
}
func NewHandler(store Store, budget time.Duration) *gin.Engine {
	// gin.New has no implicit Logger/Recovery. Order is explicit for this lesson.
	router := gin.New()
	router.HandleMethodNotAllowed = true
	router.RedirectTrailingSlash = false
	router.Use(ErrorEnvelope(), Recovery())
	router.Use(func(c *gin.Context) {
		c.Request.Body = http.MaxBytesReader(c.Writer, c.Request.Body, MaxBodyBytes)
		c.Next()
	})
	router.GET("/healthz", func(c *gin.Context) { c.JSON(200, gin.H{"status": "ok"}) })
	router.NoRoute(func(c *gin.Context) { _ = c.Error(problem(404, "route_not_found", "route not found")) })
	router.NoMethod(func(c *gin.Context) { _ = c.Error(problem(405, "method_not_allowed", "method not allowed")) })
	RegisterOrders(router, store, budget)
	return router
}
