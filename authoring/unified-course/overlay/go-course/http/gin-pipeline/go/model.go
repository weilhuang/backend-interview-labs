package lab

import (
	"context"
	"errors"
	"fmt"
	"sync"
)

const MaxBodyBytes int64 = 256

type Input struct {
	SKU      string `json:"sku" binding:"required,max=32"`
	Quantity int    `json:"quantity" binding:"min=1,max=100"`
}
type Order struct {
	ID       string `json:"id"`
	SKU      string `json:"sku"`
	Quantity int    `json:"quantity"`
}

// Store is intentionally synchronous: implementations must cooperate with ctx.
type Store interface {
	Create(context.Context, Input) (Order, error)
}
type StoreFunc func(context.Context, Input) (Order, error)

func (f StoreFunc) Create(ctx context.Context, in Input) (Order, error) { return f(ctx, in) }

type Problem struct {
	Status  int
	Code    string
	Message string
}

func (p *Problem) Error() string { return p.Code }

type ErrorBody struct {
	Error struct {
		Code    string `json:"code"`
		Message string `json:"message"`
	} `json:"error"`
}

func problem(status int, code, message string) *Problem { return &Problem{status, code, message} }
func classify(err error) *Problem {
	var p *Problem
	if errors.As(err, &p) {
		return p
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return problem(504, "deadline_exceeded", "service deadline exceeded")
	}
	if errors.Is(err, context.Canceled) {
		return problem(503, "request_canceled", "request canceled")
	}
	return problem(500, "internal_error", "internal service error")
}

// MemoryStore is a process-local demonstration, not durable storage or idempotency.
type MemoryStore struct {
	mu   sync.Mutex
	next uint64
}

func (s *MemoryStore) Create(ctx context.Context, in Input) (Order, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := ctx.Err(); err != nil {
		return Order{}, err
	}
	s.next++
	return Order{fmt.Sprintf("order-%d", s.next), in.SKU, in.Quantity}, nil
}
