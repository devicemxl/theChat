"""
engine.py - Python runtime wrapper for nxDeck + GleannVec + SentencePiece.

Calls two shared libraries via ctypes:
  1. sp_wrap.dll       - SentencePiece C++ tokenizer (C ABI)
  2. gleann_engine.dll - inference + INT8 quantization (pure C)

NxModel is an opaque pointer (void*). Python never touches its internals.
GleannVec is mirrored in ctypes because Python reads vals/scales directly.

Dependencies: ctypes (stdlib), numpy.
No torch, no transformers, no sentencepiece-pip.

Usage (context manager, recommended):

    with GleannEngine(
        engine_lib="./gleann_engine.dll",
        sp_lib="./sp_wrap.dll",
        sp_model="./embeddinggemma-300m/tokenizer.model",
        model_dir="./embeddinggemma-300m",
        pack_json="./embeddinggemma-300m.json",
        target_dim=256,
    ) as engine:
        q = engine.encode_query("how do plants get energy")
        d = engine.encode_document("Photosynthesis converts sunlight...")
        sim = engine.dot(q, d)

Copyright (c) 2026 CogNeu / David Ochoa.
"""

import ctypes
import json
import os
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resolve_path(path: str) -> str:
    """Resolve a path relative to this module's directory if not absolute."""
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    return os.path.abspath(path)


def load_json_file(path: str) -> dict:
    """Load a JSON file, returning {} if missing or malformed."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_model_config(model_dir: str) -> dict:
    """Load HuggingFace-style config.json from a model directory."""
    return load_json_file(os.path.join(model_dir, "config.json"))


# ---------------------------------------------------------------------------
# EmbeddingGemma task prefixes (from model card)
# ---------------------------------------------------------------------------

PREFIX_QUERY          = "task: search result | query: "
PREFIX_DOCUMENT       = "title: none | text: "
PREFIX_QA             = "task: question answering | query: "
PREFIX_CLASSIFICATION = "task: classification | query: "
PREFIX_CLUSTERING     = "task: clustering | query: "
PREFIX_SIMILARITY     = "task: sentence similarity | query: "
PREFIX_CODE_RETRIEVAL = "task: code retrieval | query: "


# ---------------------------------------------------------------------------
# EmbeddingGemma special tokens
# Pinned empirical ground truth: bos=2, eos=1, pad=0, unk=3.
# TODO: source from sp_wrap.dll (sp_bos_id/sp_eos_id) once available
#       to remove per-model hardcoding.
# ---------------------------------------------------------------------------

BOS_TOKEN = 2   # <bos>
EOS_TOKEN = 1   # <eos>


# ---------------------------------------------------------------------------
# GleannVec - ctypes mirror of the C struct
# NOTE: GLEANN_MAX_DIM=768 is sized for EmbeddingGemma (hidden=768).
#       Models with larger hidden dim (Qwen3 hidden=1024) require lifting this.
# ---------------------------------------------------------------------------

GLEANN_BLOCK_SIZE = 64
GLEANN_MAX_DIM    = 768
GLEANN_MAX_BLOCKS = GLEANN_MAX_DIM // GLEANN_BLOCK_SIZE  # 12


class GleannVec(ctypes.Structure):
    _fields_ = [
        ("vals",     ctypes.c_int8 * GLEANN_MAX_DIM),
        ("scales",   ctypes.c_float * GLEANN_MAX_BLOCKS),
        ("n_dims",   ctypes.c_int),
        ("n_blocks", ctypes.c_int),
    ]


# ---------------------------------------------------------------------------
# SentencePiece wrapper (sp_wrap.dll)
# ---------------------------------------------------------------------------

class SPTokenizer:
    """Wraps sp_wrap.dll - opaque sp_handle*."""

    def __init__(self, lib_path: str, model_path: str):
        # Initialize handle to None FIRST so __del__ is safe even if __init__ fails.
        self._handle = None
        self._lib = None

        lib_path   = resolve_path(lib_path)
        model_path = resolve_path(model_path)

        if not os.path.exists(lib_path):
            raise FileNotFoundError(f"Tokenizer library not found: {lib_path}")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Tokenizer model not found: {model_path}")

        # winmode=0 restores classic LoadLibrary search on Windows (Python 3.8+
        # changed the default to a stricter search); ignored on Linux/macOS.
        self._lib = ctypes.CDLL(lib_path, winmode=0)
        self._setup_functions()

        self._handle = self._lib.sp_create(model_path.encode("utf-8"))
        if not self._handle:
            raise RuntimeError(f"sp_create failed: {model_path}")

    def _setup_functions(self):
        lib = self._lib

        lib.sp_create.argtypes = [ctypes.c_char_p]
        lib.sp_create.restype  = ctypes.c_void_p

        lib.sp_destroy.argtypes = [ctypes.c_void_p]
        lib.sp_destroy.restype  = None

        lib.sp_encode_ids.argtypes = [
            ctypes.c_void_p,                                # handle
            ctypes.c_char_p,                                # input text (UTF-8)
            ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),   # out_ids
            ctypes.POINTER(ctypes.c_size_t),                # out_len
        ]
        lib.sp_encode_ids.restype = ctypes.c_int

        lib.sp_free.argtypes = [ctypes.c_void_p]
        lib.sp_free.restype  = None

    def encode(self, text: str) -> list[int]:
        """Tokenize text into token IDs. Does NOT prepend BOS or append EOS."""
        ids_ptr = ctypes.POINTER(ctypes.c_int)()
        length  = ctypes.c_size_t(0)

        status = self._lib.sp_encode_ids(
            self._handle,
            text.encode("utf-8"),
            ctypes.byref(ids_ptr),
            ctypes.byref(length),
        )
        if status != 0:
            raise RuntimeError(f"sp_encode_ids failed (status={status})")

        n = length.value
        result = [ids_ptr[i] for i in range(n)]
        self._lib.sp_free(ids_ptr)
        return result

    def close(self):
        if self._handle and self._lib is not None:
            self._lib.sp_destroy(self._handle)
            self._handle = None

    def __del__(self):
        # Best-effort cleanup; do not rely on __del__ for correctness.
        try:
            self.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# GleannEngine - full pipeline
# ---------------------------------------------------------------------------

class GleannEngine:
    """
    Full pipeline: text -> tokens -> FP32 embedding -> INT8 quantized vector.

    Not thread-safe: instances hold a single reusable FP32 buffer.
    For concurrent use, instantiate one engine per thread or add a lock.

    Prefer using as a context manager to guarantee cleanup on exceptions:
        with GleannEngine(...) as engine:
            ...
    """

    def __init__(
        self,
        engine_lib: str,
        sp_lib: str,
        sp_model: str,
        model_dir: str,
        pack_json: str | None = None,
        target_dim: int = 256,
        normalize: bool = True,
    ):
        # Initialize all state to None so __del__/close are safe if __init__ fails.
        self._handle = None
        self._lib    = None
        self._tok    = None

        self.target_dim = target_dim
        self.normalize  = normalize

        engine_lib = resolve_path(engine_lib)
        if not os.path.exists(engine_lib):
            raise FileNotFoundError(f"Engine library not found: {engine_lib}")
        self._lib = ctypes.CDLL(engine_lib, winmode=0)
        self._setup_engine_functions()

        # Detect AVX2 availability at load time; probe by attempting to call
        # gleann_dot_avx2 on a zero-vector during first use. For now we assume
        # available if the symbol resolved; fallback triggers on OSError.
        self._dot_fn = self._lib.gleann_dot_avx2
        self._dot_scalar = self._lib.gleann_dot

        # Tokenizer (constructed second; if this raises, engine lib is loaded
        # but nothing else is allocated yet - safe to drop).
        try:
            self._tok = SPTokenizer(sp_lib, sp_model)
        except Exception:
            self._lib = None  # release DLL reference
            raise

        # Resolve model directory; optionally materialize nxdeck.json from pack.
        self._model_dir = resolve_path(model_dir)
        if not os.path.exists(self._model_dir):
            self._tok.close(); self._tok = None
            raise FileNotFoundError(f"Model directory not found: {self._model_dir}")

        self._pack_json    = None
        self._pack_config  = {}
        self._nxdeck_json  = os.path.join(self._model_dir, "nxdeck.json")

        if pack_json is not None:
            self._pack_json = resolve_path(pack_json)
            if not os.path.exists(self._pack_json):
                self._tok.close(); self._tok = None
                raise FileNotFoundError(f"Pack JSON not found: {self._pack_json}")
            self._pack_config = load_json_file(self._pack_json)
            if not os.path.exists(self._nxdeck_json):
                with open(self._nxdeck_json, "w", encoding="utf-8") as f:
                    json.dump(self._pack_config, f, indent=2)

        # Create model (opaque void*). If this fails, close the tokenizer to
        # avoid leaking the SentencePiece handle.
        self._handle = self._lib.nxpy_create(self._model_dir.encode("utf-8"))
        if not self._handle:
            self._tok.close(); self._tok = None
            raise RuntimeError(
                f"nxpy_create failed: {self._model_dir}. "
                "Check that this path points to a valid nxDeck embedding model."
            )

        # Query model info.
        self.hidden_dim = self._lib.nxpy_hidden_dim(self._handle)
        self.max_seq    = self._lib.nxpy_max_seq(self._handle)

        self._config = (load_model_config(self._model_dir)
                        or self._pack_config
                        or {})

        if self.target_dim <= 0 or self.target_dim > self.hidden_dim:
            raise ValueError(
                f"target_dim must be in [1, hidden_dim={self.hidden_dim}], "
                f"got {self.target_dim}"
            )
        if self.target_dim % GLEANN_BLOCK_SIZE != 0:
            raise ValueError(
                f"target_dim must be a multiple of {GLEANN_BLOCK_SIZE}, "
                f"got {self.target_dim}"
            )

        # nxDeck models embed at full hidden_dim; we truncate + renormalize
        # afterwards (Matryoshka Representation Learning: EmbeddingGemma
        # is trained so leading-N truncated slices remain semantically valid).
        self._embed_dim = self.hidden_dim
        self._fp32_buf  = np.zeros(self._embed_dim, dtype=np.float32)

    def _setup_engine_functions(self):
        lib = self._lib

        # --- nxpy bridge ---
        lib.nxpy_create.argtypes = [ctypes.c_char_p]
        lib.nxpy_create.restype  = ctypes.c_void_p

        lib.nxpy_embed.argtypes = [
            ctypes.c_void_p,                    # handle
            ctypes.POINTER(ctypes.c_int32),     # tokens
            ctypes.c_int,                       # n_tokens
            ctypes.POINTER(ctypes.c_float),     # output
            ctypes.c_int,                       # target_dim
        ]
        lib.nxpy_embed.restype = ctypes.c_int

        lib.nxpy_hidden_dim.argtypes = [ctypes.c_void_p]
        lib.nxpy_hidden_dim.restype  = ctypes.c_int

        lib.nxpy_max_seq.argtypes = [ctypes.c_void_p]
        lib.nxpy_max_seq.restype  = ctypes.c_int

        lib.nxpy_destroy.argtypes = [ctypes.c_void_p]
        lib.nxpy_destroy.restype  = None

        # --- gleann_vec ---
        lib.gleann_quantize.argtypes = [
            ctypes.POINTER(ctypes.c_float),     # src
            ctypes.POINTER(GleannVec),          # dst
            ctypes.c_int,                       # n_dims
        ]
        lib.gleann_quantize.restype = None

        lib.gleann_dot.argtypes = [
            ctypes.POINTER(GleannVec),
            ctypes.POINTER(GleannVec),
        ]
        lib.gleann_dot.restype = ctypes.c_float

        lib.gleann_dot_avx2.argtypes = [
            ctypes.POINTER(GleannVec),
            ctypes.POINTER(GleannVec),
        ]
        lib.gleann_dot_avx2.restype = ctypes.c_float

        lib.gleann_dequantize.argtypes = [
            ctypes.POINTER(GleannVec),
            ctypes.POINTER(ctypes.c_float),
        ]
        lib.gleann_dequantize.restype = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _embed_raw(self, tokens: list[int]) -> np.ndarray:
        """Token IDs (with BOS/EOS already included) -> FP32 embedding.

        Runs embedding at hidden_dim, truncates to target_dim (MRL slice),
        and L2-renormalizes when normalize=True so downstream cosine
        similarity is well-defined on the truncated slice.
        """
        tok_arr = (ctypes.c_int32 * len(tokens))(*tokens)
        out_ptr = self._fp32_buf.ctypes.data_as(ctypes.POINTER(ctypes.c_float))

        ret = self._lib.nxpy_embed(
            self._handle, tok_arr, len(tokens),
            out_ptr, self._embed_dim,
        )
        if ret != 0:
            model_type = self._config.get("model_type")
            raise RuntimeError(
                f"nxpy_embed failed (ret={ret}). "
                "This often means the loaded model is a decoder, not an "
                f"encoder/embedding model. model_type={model_type!r}."
            )

        vec = self._fp32_buf[: self.target_dim].copy()

        # L2 renormalize after MRL truncation. Cosine similarity is only
        # meaningful on unit-norm vectors; truncating a normalized 768-D
        # vector to 256-D produces a shorter (non-unit) vector unless we
        # renormalize. Downstream (HNSW cosine, gleann_dot as cosine proxy)
        # assumes unit norm.
        if self.normalize:
            n = np.linalg.norm(vec)
            if n > 1e-12:
                vec /= n

        return vec

    def _quantize(self, fp32: np.ndarray) -> GleannVec:
        """FP32 numpy array -> GleannVec."""
        qvec = GleannVec()
        fp32_ptr = fp32.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        self._lib.gleann_quantize(fp32_ptr, ctypes.byref(qvec), self.target_dim)
        return qvec

    # ------------------------------------------------------------------
    # Public API - tokenization
    # ------------------------------------------------------------------

    def tokenize(self, text: str) -> list[int]:
        """Text -> token IDs without BOS/EOS (via sp_wrap.dll)."""
        return self._tok.encode(text)

    # ------------------------------------------------------------------
    # Public API - FP32 embeddings
    # ------------------------------------------------------------------

    def embed_fp32(self, text: str) -> np.ndarray:
        """Text -> FP32 embedding (target_dim). Adds BOS/EOS automatically."""
        tokens = self._tok.encode(text)
        tokens = [BOS_TOKEN] + tokens + [EOS_TOKEN]
        return self._embed_raw(tokens)

    def embed_tokens_fp32(self, tokens: list[int]) -> np.ndarray:
        """Token IDs -> FP32 embedding. Caller must include BOS/EOS."""
        return self._embed_raw(tokens)

    def embed_query(self, text: str) -> np.ndarray:
        """Query text -> FP32 embedding with retrieval query prefix."""
        return self.embed_fp32(PREFIX_QUERY + text)

    def embed_document(self, text: str) -> np.ndarray:
        """Document text -> FP32 embedding with document prefix."""
        return self.embed_fp32(PREFIX_DOCUMENT + text)

    def embed_similarity(self, text: str) -> np.ndarray:
        """Text -> FP32 embedding with symmetric similarity prefix."""
        return self.embed_fp32(PREFIX_SIMILARITY + text)

    # ------------------------------------------------------------------
    # Public API - INT8 quantized vectors
    # ------------------------------------------------------------------

    def encode(self, text: str) -> GleannVec:
        return self._quantize(self.embed_fp32(text))

    def encode_query(self, text: str) -> GleannVec:
        return self._quantize(self.embed_query(text))

    def encode_document(self, text: str) -> GleannVec:
        return self._quantize(self.embed_document(text))

    def encode_similarity(self, text: str) -> GleannVec:
        return self._quantize(self.embed_similarity(text))

    def encode_batch(self, texts: list[str]) -> list[GleannVec]:
        return [self.encode(t) for t in texts]

    def encode_documents(self, texts: list[str]) -> list[GleannVec]:
        return [self.encode_document(t) for t in texts]

    # ------------------------------------------------------------------
    # Public API - comparison & search
    # ------------------------------------------------------------------

    def dot(self, a: GleannVec, b: GleannVec) -> float:
        """INT8 dot product; cosine similarity when inputs are unit-norm.

        Prefers AVX2 kernel; falls back to scalar on OSError (non-x86 CPUs
        such as ARM64/M1 do not have AVX2).
        """
        try:
            return self._dot_fn(ctypes.byref(a), ctypes.byref(b))
        except OSError:
            # AVX2 not available on this CPU; permanently switch to scalar.
            self._dot_fn = self._dot_scalar
            return self._dot_fn(ctypes.byref(a), ctypes.byref(b))

    def similarity(self, text_a: str, text_b: str) -> float:
        qa = self.encode(text_a)
        qb = self.encode(text_b)
        return self.dot(qa, qb)

    def search(self, query: str, corpus: list[GleannVec],
               top_k: int = 5) -> list[tuple[int, float]]:
        """Brute-force asymmetric retrieval over an in-memory corpus."""
        q = self.encode_query(query)
        scored = [(i, self.dot(q, doc)) for i, doc in enumerate(corpus)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Release engine handle and tokenizer. Safe to call more than once."""
        if getattr(self, "_handle", None) and getattr(self, "_lib", None):
            self._lib.nxpy_destroy(self._handle)
            self._handle = None
        if getattr(self, "_tok", None):
            self._tok.close()
            self._tok = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # do not suppress exceptions

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def __repr__(self):
        return (
            f"GleannEngine(dim={self.target_dim}, "
            f"hidden={self.hidden_dim}, max_seq={self.max_seq}, "
            f"normalize={self.normalize})"
        )
