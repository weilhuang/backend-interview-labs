package lab

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"testing/synctest"
	"time"
)

const orderPath = "/orders"
const validJSON = `{"sku":"book","quantity":2}`

func request(method, path, body string) *http.Request {
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	r.Header.Set("Content-Type", "application/json; charset=utf-8")
	r.Header.Set("X-Lab-Key", "training-key")
	return r
}
func assertResponse(t *testing.T, rr *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	if rr.Code != status {
		t.Fatalf("HTTP_STATUS want=%d got=%d body=%s", status, rr.Code, rr.Body.String())
	}
	if !strings.HasPrefix(rr.Header().Get("Content-Type"), "application/json") {
		t.Fatalf("HTTP_CONTENT_TYPE %q", rr.Header().Get("Content-Type"))
	}
	if code != "" {
		var body ErrorBody
		if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil {
			t.Fatalf("HTTP_SINGLE_JSON %v body=%s", err, rr.Body.String())
		}
		if body.Error.Code != code || body.Error.Message == "" {
			t.Fatalf("HTTP_ERROR_CODE want=%s got=%+v", code, body)
		}
	}
}
func TestRequestContract(t *testing.T) {
	cases := []struct {
		name, body, media string
		status            int
		code              string
		want              Input // independent expected normalized request, never inferred from Store capture
	}{
		{"valid", validJSON, "application/json", 201, "", Input{"book", 2}},
		{"trim", `{"sku":"  图书  ","quantity":1}`, "application/json; charset=utf-8", 201, "", Input{"图书", 1}},
		{"quantity_max", `{"sku":"x","quantity":100}`, "application/json", 201, "", Input{"x", 100}},
		{"exact_byte_limit", validJSON + strings.Repeat(" ", int(MaxBodyBytes)-len(validJSON)), "application/json", 201, "", Input{"book", 2}},
		{"over_byte_limit", validJSON + strings.Repeat(" ", int(MaxBodyBytes)-len(validJSON)+1), "application/json", 413, "body_too_large", Input{}},
		{"large_value", `{"sku":"` + strings.Repeat("a", 300) + `","quantity":1}`, "application/json", 413, "body_too_large", Input{}},
		{"missing_media", validJSON, "", 415, "unsupported_media_type", Input{}},
		{"wrong_media", validJSON, "text/plain", 415, "unsupported_media_type", Input{}},
		{"trailing_semicolon_media", validJSON, "application/json;", 201, "", Input{"book", 2}},
		{"malformed_json", `{"sku":`, "application/json", 400, "invalid_json", Input{}},
		{"empty_body", "", "application/json", 400, "invalid_json", Input{}},
		{"unknown_field", `{"sku":"x","quantity":1,"admin":true}`, "application/json", 400, "invalid_json", Input{}},
		{"extra_value", validJSON + ` {}`, "application/json", 400, "invalid_json", Input{}},
		{"extra_scalar", validJSON + ` true`, "application/json", 400, "invalid_json", Input{}},
		{"garbage_tail", validJSON + ` !!!`, "application/json", 400, "invalid_json", Input{}},
		{"wrong_type", `{"sku":"x","quantity":"2"}`, "application/json", 400, "invalid_json", Input{}},
		{"null_object", `null`, "application/json", 422, "invalid_input", Input{}},
		{"missing_quantity", `{"sku":"x"}`, "application/json", 422, "invalid_input", Input{}},
		{"zero_quantity", `{"sku":"x","quantity":0}`, "application/json", 422, "invalid_input", Input{}},
		{"negative_quantity", `{"sku":"x","quantity":-1}`, "application/json", 422, "invalid_input", Input{}},
		{"large_quantity", `{"sku":"x","quantity":101}`, "application/json", 422, "invalid_input", Input{}},
		{"blank_sku", `{"sku":" \t ","quantity":1}`, "application/json", 422, "invalid_input", Input{}},
		{"sku_32_runes", `{"sku":"` + strings.Repeat("书", 32) + `","quantity":1}`, "application/json", 201, "", Input{strings.Repeat("书", 32), 1}},
		{"sku_33_runes", `{"sku":"` + strings.Repeat("书", 33) + `","quantity":1}`, "application/json", 422, "invalid_input", Input{}},
		{"mixed_malformed_oversize", "!" + strings.Repeat("x", 300), "application/json", 400, "invalid_json", Input{}},
		{"mixed_unknown_oversize", `{"bad":true}` + strings.Repeat(" ", 300), "application/json", 400, "invalid_json", Input{}},
		{"mixed_extra_value_oversize", validJSON + ` {}` + strings.Repeat(" ", 300), "application/json", 400, "invalid_json", Input{}},
		{"mixed_media_oversize", "!" + strings.Repeat("x", 300), "text/plain", 415, "unsupported_media_type", Input{}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			calls := 0
			var got Input
			store := StoreFunc(func(ctx context.Context, in Input) (Order, error) {
				calls++
				got = in
				return Order{"order-7", in.SKU, in.Quantity}, nil
			})
			r := request("POST", orderPath, tc.body)
			r.Header.Set("Content-Type", tc.media)
			r.ContentLength = -1 // no trusting advertised Content-Length; the reader enforces actual bytes
			rr := httptest.NewRecorder()
			NewHandler(store, time.Second).ServeHTTP(rr, r)
			assertResponse(t, rr, tc.status, tc.code)
			if tc.status == 201 {
				if calls != 1 {
					t.Fatalf("SERVICE_CALLS want1 got%d", calls)
				}
				if got != tc.want {
					t.Fatalf("REQUEST_FORWARDING want=%+v got=%+v", tc.want, got)
				}
				wantOrder := Order{"order-7", tc.want.SKU, tc.want.Quantity}
				var body Order
				// Unmarshal also rejects a second response JSON value or trailing garbage.
				if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil || body != wantOrder {
					t.Fatalf("HTTP_SUCCESS_BODY want=%+v got=%+v err=%v", wantOrder, body, err)
				}
			} else if calls != 0 {
				t.Fatalf("SIDE_EFFECT_BEFORE_VALIDATION calls=%d", calls)
			}
		})
	}
}
func TestContextContract(t *testing.T) {
	t.Run("inherits_and_releases", func(t *testing.T) {
		type key struct{}
		parent := context.WithValue(context.Background(), key{}, "trace-7")
		var child context.Context
		store := StoreFunc(func(ctx context.Context, in Input) (Order, error) {
			child = ctx
			if ctx.Value(key{}) != "trace-7" {
				t.Fatal("CONTEXT parent value lost")
			}
			if _, ok := ctx.Deadline(); !ok {
				t.Fatal("CONTEXT deadline missing")
			}
			return Order{"order-1", in.SKU, in.Quantity}, nil
		})
		rr := httptest.NewRecorder()
		NewHandler(store, time.Hour).ServeHTTP(rr, request("POST", orderPath, validJSON).WithContext(parent))
		assertResponse(t, rr, 201, "")
		if child == nil || !errors.Is(child.Err(), context.Canceled) {
			t.Fatalf("CONTEXT cancel not released: %v", child)
		}
	})
	t.Run("already_canceled", func(t *testing.T) {
		parent, cancel := context.WithCancel(context.Background())
		cancel()
		calls := 0
		store := StoreFunc(func(context.Context, Input) (Order, error) { calls++; return Order{}, nil })
		rr := httptest.NewRecorder()
		NewHandler(store, time.Hour).ServeHTTP(rr, request("POST", orderPath, validJSON).WithContext(parent))
		assertResponse(t, rr, 503, "request_canceled")
		if calls != 0 {
			t.Fatal("CONTEXT called store after cancellation")
		}
	})
	t.Run("zero_budget", func(t *testing.T) {
		calls := 0
		store := StoreFunc(func(context.Context, Input) (Order, error) { calls++; return Order{}, nil })
		rr := httptest.NewRecorder()
		NewHandler(store, 0).ServeHTTP(rr, request("POST", orderPath, validJSON))
		assertResponse(t, rr, 504, "deadline_exceeded")
		if calls != 0 {
			t.Fatal("CONTEXT called store after deadline")
		}
	})
	t.Run("downstream_deadline", func(t *testing.T) {
		store := StoreFunc(func(ctx context.Context, in Input) (Order, error) {
			select {
			case <-ctx.Done():
				return Order{}, fmt.Errorf("lookup: %w", ctx.Err())
			case <-time.After(5 * time.Second):
				return Order{}, errors.New("TEST_GUARD context not propagated")
			}
		})
		rr := httptest.NewRecorder()
		NewHandler(store, time.Millisecond).ServeHTTP(rr, request("POST", orderPath, validJSON))
		// Assert semantic error, never elapsed milliseconds or scheduler speed.
		assertResponse(t, rr, 504, "deadline_exceeded")
	})
	t.Run("canceled_after_store_success", func(t *testing.T) {
		parent, cancel := context.WithCancel(context.Background())
		defer cancel()
		calls := 0
		store := StoreFunc(func(ctx context.Context, in Input) (Order, error) {
			calls++
			cancel() // WithCancel -> WithTimeout propagation is synchronous for this standard context tree.
			// A broken implementation may derive from Background. Never wait on its unrelated Done.
			if !errors.Is(ctx.Err(), context.Canceled) {
				t.Fatalf("POSTCHECK_PARENT child did not inherit cancellation: %v", ctx.Err())
			}
			select {
			case <-ctx.Done(): // already closed; this is deliberately a nonblocking assertion
			default:
				t.Fatal("POSTCHECK_PARENT child Done is not closed after parent cancel")
			}
			return Order{"already-produced", in.SKU, in.Quantity}, nil
		})
		rr := httptest.NewRecorder()
		NewHandler(store, time.Hour).ServeHTTP(rr, request("POST", orderPath, validJSON).WithContext(parent))
		if calls != 1 {
			t.Fatalf("POSTCHECK_SETUP store calls=%d", calls)
		}
		assertResponse(t, rr, 503, "request_canceled")
	})
	t.Run("deadline_after_store_success", func(t *testing.T) {
		// Go 1.27.1's synctest fake clock advances only when the bubble is durably blocked.
		// This test has no network or external process and makes no wall-clock assertion.
		synctest.Test(t, func(t *testing.T) {
			calls := 0
			store := StoreFunc(func(ctx context.Context, in Input) (Order, error) {
				calls++
				<-ctx.Done()
				if !errors.Is(ctx.Err(), context.DeadlineExceeded) {
					t.Fatalf("POSTCHECK_SETUP %v", ctx.Err())
				}
				return Order{"already-produced", in.SKU, in.Quantity}, nil
			})
			rr := httptest.NewRecorder()
			NewHandler(store, time.Second).ServeHTTP(rr, request("POST", orderPath, validJSON))
			if calls != 1 {
				t.Fatalf("POSTCHECK_SETUP store calls=%d", calls)
			}
			assertResponse(t, rr, 504, "deadline_exceeded")
		})
	})

	t.Run("internal_error_redacted", func(t *testing.T) {
		store := StoreFunc(func(context.Context, Input) (Order, error) { return Order{}, errors.New("db password=do-not-leak") })
		rr := httptest.NewRecorder()
		NewHandler(store, time.Second).ServeHTTP(rr, request("POST", orderPath, validJSON))
		assertResponse(t, rr, 500, "internal_error")
		if strings.Contains(rr.Body.String(), "password") {
			t.Fatal("ERROR_LEAK exposed internal detail")
		}
	})
	t.Run("wrapped_cancellation", func(t *testing.T) {
		store := StoreFunc(func(context.Context, Input) (Order, error) { return Order{}, fmt.Errorf("store: %w", context.Canceled) })
		rr := httptest.NewRecorder()
		NewHandler(store, time.Second).ServeHTTP(rr, request("POST", orderPath, validJSON))
		assertResponse(t, rr, 503, "request_canceled")
	})
}
func TestRouting(t *testing.T) {
	h := NewHandler(&MemoryStore{}, time.Second)
	for _, tc := range []struct {
		method, path string
		status       int
	}{{"GET", "/healthz", 200}, {"GET", orderPath, 405}, {"POST", "/missing", 404}} {
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, request(tc.method, tc.path, validJSON))
		if rr.Code != tc.status {
			t.Fatalf("ROUTING %s %s want%d got%d", tc.method, tc.path, tc.status, rr.Code)
		}
	}
}
func TestActualHTTP(t *testing.T) {
	observed := make(chan Input, 4)
	memory := &MemoryStore{}
	store := StoreFunc(func(ctx context.Context, in Input) (Order, error) {
		observed <- in
		return memory.Create(ctx, in)
	})
	server := httptest.NewServer(NewHandler(store, time.Second))
	defer server.Close()
	client := server.Client()
	client.Timeout = 5 * time.Second
	defer client.CloseIdleConnections()
	for _, tc := range []struct {
		name, body string
		want       Input
		id         string
	}{
		{"unicode_trim_quantity_7", `{"sku":"  毛笔  ","quantity":7}`, Input{"毛笔", 7}, "order-1"},
		{"preserve_case_internal_space_quantity_99", `{"sku":"A SKU-9","quantity":99}`, Input{"A SKU-9", 99}, "order-2"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			r, err := http.NewRequest("POST", server.URL+orderPath, strings.NewReader(tc.body))
			if err != nil {
				t.Fatal(err)
			}
			r.Header.Set("Content-Type", "application/json")
			r.Header.Set("X-Lab-Key", "training-key")
			response, err := client.Do(r)
			if err != nil {
				t.Fatal(err)
			}
			payload, err := io.ReadAll(response.Body)
			response.Body.Close()
			if err != nil {
				t.Fatal(err)
			}
			if response.StatusCode != 201 || !strings.HasPrefix(response.Header.Get("Content-Type"), "application/json") {
				t.Fatalf("ACTUAL_HTTP status=%d content-type=%q body=%s", response.StatusCode, response.Header.Get("Content-Type"), payload)
			}
			select {
			case got := <-observed:
				if got != tc.want {
					t.Fatalf("ACTUAL_HTTP_FORWARDING want=%+v got=%+v", tc.want, got)
				}
			default:
				t.Fatal("ACTUAL_HTTP Store was not observed before response")
			}
			wantOrder := Order{tc.id, tc.want.SKU, tc.want.Quantity}
			var order Order
			if err := json.Unmarshal(payload, &order); err != nil || order != wantOrder {
				t.Fatalf("ACTUAL_HTTP_RESPONSE want=%+v got=%+v err=%v body=%s", wantOrder, order, err, payload)
			}
		})
	}
}
func TestServiceResultPreserved(t *testing.T) {
	wantInput := Input{"CLIENT SKU", 17}
	wantOrder := Order{"service-id-91", "CANONICAL SKU", 23}
	calls := 0
	store := StoreFunc(func(ctx context.Context, in Input) (Order, error) {
		calls++
		if in != wantInput {
			t.Fatalf("SERVICE_INPUT want=%+v got=%+v", wantInput, in)
		}
		return wantOrder, nil
	})
	rr := httptest.NewRecorder()
	NewHandler(store, time.Second).ServeHTTP(rr, request("POST", orderPath, `{"sku":" CLIENT SKU ","quantity":17}`))
	assertResponse(t, rr, 201, "")
	var got Order
	if err := json.Unmarshal(rr.Body.Bytes(), &got); err != nil || got != wantOrder || calls != 1 {
		t.Fatalf("SERVICE_RESULT want=%+v got=%+v calls=%d err=%v", wantOrder, got, calls, err)
	}
}
func TestClientCancellation(t *testing.T) {
	started := make(chan struct{})
	observed := make(chan error, 1)
	store := StoreFunc(func(ctx context.Context, in Input) (Order, error) {
		close(started)
		select {
		case <-ctx.Done():
			observed <- ctx.Err()
			return Order{}, ctx.Err()
		case <-time.After(5 * time.Second):
			observed <- errors.New("TEST_GUARD cancel missing")
			return Order{}, errors.New("cancel missing")
		}
	})
	server := httptest.NewServer(NewHandler(store, time.Hour))
	defer server.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	r, _ := http.NewRequestWithContext(ctx, "POST", server.URL+orderPath, strings.NewReader(validJSON))
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("X-Lab-Key", "training-key")
	client := server.Client()
	client.Timeout = 8 * time.Second
	defer client.CloseIdleConnections()
	done := make(chan error, 1)
	go func() {
		res, err := client.Do(r)
		if res != nil {
			io.Copy(io.Discard, res.Body)
			res.Body.Close()
		}
		done <- err
	}()
	select {
	case <-started:
	case <-time.After(5 * time.Second):
		t.Fatal("CANCEL service not reached")
	}
	cancel()
	select {
	case err := <-observed:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("CANCEL parent lost: %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("CANCEL store did not observe disconnect")
	}
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("CANCEL client error %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("CANCEL client did not finish")
	}
}
func TestConcurrentMemoryStore(t *testing.T) {
	store := &MemoryStore{}
	var wg sync.WaitGroup
	var bad atomic.Int32
	ids := make(chan string, 24)
	for range 24 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			o, e := store.Create(context.Background(), Input{"x", 1})
			if e != nil {
				bad.Add(1)
				return
			}
			ids <- o.ID
		}()
	}
	wg.Wait()
	close(ids)
	seen := map[string]bool{}
	for id := range ids {
		if seen[id] {
			bad.Add(1)
		}
		seen[id] = true
	}
	if bad.Load() != 0 || len(seen) != 24 {
		t.Fatalf("STORE race/duplicate %d ids %d bad", len(seen), bad.Load())
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := store.Create(ctx, Input{"x", 1}); !errors.Is(err, context.Canceled) {
		t.Fatalf("STORE canceled context %v", err)
	}
}
