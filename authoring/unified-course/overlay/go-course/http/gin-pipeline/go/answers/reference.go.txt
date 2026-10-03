package lab

import (
	"context"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
)

var _ = []any{context.WithTimeout, http.StatusCreated}

// RequireDemoKey demonstrates control flow, not production identity/security.
func RequireDemoKey() gin.HandlerFunc {
	return func(c *gin.Context) {
		// BEGIN gate
		if c.GetHeader("X-Lab-Key") != "training-key" {
			_ = c.Error(problem(401, "demo_key_required", "send the documented demonstration key"))
			c.Abort()
			return
		}
		c.Next()
		// END gate
	}
}

// ErrorEnvelope runs after downstream work and owns unwritten errors only.
func ErrorEnvelope() gin.HandlerFunc {
	return func(c *gin.Context) {
		// BEGIN errors
		c.Next()
		if len(c.Errors) == 0 || c.Writer.Written() {
			return
		}
		p := classify(c.Errors.Last().Err)
		var body ErrorBody
		body.Error.Code = p.Code
		body.Error.Message = p.Message
		c.JSON(p.Status, body)
		// END errors
	}
}
func RegisterOrders(router *gin.Engine, store Store, budget time.Duration) {
	// BEGIN routes
	group := router.Group("/v1")
	group.Use(RequireDemoKey())
	group.POST("/orders", func(c *gin.Context) {
		var input Input
		if err := c.ShouldBindWith(&input, StrictJSON{}); err != nil {
			_ = c.Error(err)
			c.Abort()
			return
		}
		ctx, cancel := context.WithTimeout(c.Request.Context(), budget)
		defer cancel()
		if err := ctx.Err(); err != nil {
			_ = c.Error(err)
			c.Abort()
			return
		}
		order, err := store.Create(ctx, input)
		if err == nil {
			err = ctx.Err()
		}
		if err != nil {
			_ = c.Error(err)
			c.Abort()
			return
		}
		c.JSON(http.StatusCreated, order)
	})
	// END routes
}
