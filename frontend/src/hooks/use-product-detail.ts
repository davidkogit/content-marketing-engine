/**
 * useProductDetail — fetches product data and manages generation,
 * claims, documents, and versions for the product detail page.
 *
 * Must be called inside an authenticated context (apiClient handles JWT).
 */

import { useState, useCallback, useEffect } from "react";
import {
  products,
  generation,
  documents,
  claims,
  versions,
} from "@/lib/api-endpoints";
import type {
  ProductResponse,
  GeneratedResponse,
  GenerateRequest,
  GenerationType,
  ProductClaim,
  ClaimUpdate,
  ProductDocument,
  DocumentCreate,
} from "@/types";

interface ProductDetailState {
  product: ProductResponse | null;
  generatedResult: GeneratedResponse | null;
  isLoading: boolean;
  isGenerating: boolean;
  error: string | null;
}

interface UseProductDetailReturn extends ProductDetailState {
  /** Trigger content generation for the given generation type. */
  generate: (genType: GenerationType) => Promise<GeneratedResponse>;
  /** Add a new source document to the product. */
  addDocument: (body: DocumentCreate) => Promise<ProductDocument>;
  /** Remove a document by its ID. */
  removeDocument: (documentId: number) => Promise<void>;
  /** Update an existing claim (editor+). */
  updateClaim: (
    claimId: number,
    body: ClaimUpdate,
  ) => Promise<ProductClaim>;
  /** Restore a previous version by version number. */
  restoreVersion: (versionNumber: number) => Promise<void>;
  /** Reload the full product detail from the server. */
  refresh: () => Promise<void>;
}

/**
 * Core hook for the product detail page.
 *
 * @param productId - The numeric ID of the product to load and manage.
 */
export function useProductDetail(
  productId: number | null,
): UseProductDetailReturn {
  const [state, setState] = useState<ProductDetailState>({
    product: null,
    generatedResult: null,
    isLoading: false,
    isGenerating: false,
    error: null,
  });

  // ── Helpers ──────────────────────────────────────────────────────────────

  const setError = useCallback((msg: string) => {
    setState((prev) => ({ ...prev, error: msg }));
  }, []);

  const clearError = useCallback(() => {
    setState((prev) => ({ ...prev, error: null }));
  }, []);

  // ── Fetch Product Detail ─────────────────────────────────────────────────

  const refresh = useCallback(async () => {
    if (productId === null) return;

    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const data = await products.get(productId);
      setState((prev) => ({
        ...prev,
        product: data,
        isLoading: false,
      }));
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to load product";
      setState((prev) => ({ ...prev, isLoading: false, error: message }));
    }
  }, [productId, setError]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // ── Generate Content ─────────────────────────────────────────────────────

  const generate = useCallback(
    async (genType: GenerationType): Promise<GeneratedResponse> => {
      if (productId === null) {
        throw new Error("No product selected");
      }
      clearError();
      setState((prev) => ({ ...prev, isGenerating: true }));
      try {
        const body: GenerateRequest = { generation_type: genType };
        const result = await generation.sync(productId, body);
        setState((prev) => ({
          ...prev,
          generatedResult: result,
          isGenerating: false,
        }));
        return result;
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Generation failed";
        setState((prev) => ({
          ...prev,
          isGenerating: false,
          error: message,
        }));
        throw err;
      }
    },
    [productId, clearError],
  );

  // ── Documents ────────────────────────────────────────────────────────────

  const addDocument = useCallback(
    async (body: DocumentCreate): Promise<ProductDocument> => {
      if (productId === null) throw new Error("No product selected");
      clearError();
      try {
        const doc = await documents.create(productId, body);
        // Optimistically add to local state so UI reflects immediately.
        setState((prev) => {
          if (!prev.product) return prev;
          const productDocs = prev.product.documents ?? [];
          const ref = {
            id: doc.id,
            title: doc.title,
            url: doc.url,
            doc_type: doc.doc_type,
          };
          return {
            ...prev,
            product: { ...prev.product, documents: [...productDocs, ref] },
          };
        });
        return doc;
      } catch (err: unknown) {
        setError(
          err instanceof Error ? err.message : "Failed to add document",
        );
        throw err;
      }
    },
    [productId, clearError, setError],
  );

  const removeDocument = useCallback(
    async (documentId: number): Promise<void> => {
      clearError();
      try {
        await documents.delete(documentId);
        // Remove from local state.
        setState((prev) => {
          if (!prev.product) return prev;
          return {
            ...prev,
            product: {
              ...prev.product,
              documents: (prev.product.documents ?? []).filter(
                (d) => d.id !== documentId,
              ),
            },
          };
        });
      } catch (err: unknown) {
        setError(
          err instanceof Error ? err.message : "Failed to remove document",
        );
        throw err;
      }
    },
    [clearError, setError],
  );

  // ── Claims ───────────────────────────────────────────────────────────────

  const updateClaim = useCallback(
    async (
      claimId: number,
      body: ClaimUpdate,
    ): Promise<ProductClaim> => {
      clearError();
      try {
        const updated = await claims.update(claimId, body);
        setState((prev) => {
          if (!prev.product) return prev;
          return {
            ...prev,
            product: {
              ...prev.product,
              claims: (prev.product.claims ?? []).map((c) =>
                c.id === claimId
                  ? { ...c, claim_text: updated.claim_text, status: updated.status ?? c.status }
                  : c,
              ),
            },
          };
        });
        return updated;
      } catch (err: unknown) {
        setError(
          err instanceof Error ? err.message : "Failed to update claim",
        );
        throw err;
      }
    },
    [clearError, setError],
  );

  // ── Versions ─────────────────────────────────────────────────────────────

  const restoreVersion = useCallback(
    async (versionNumber: number): Promise<void> => {
      if (productId === null) throw new Error("No product selected");
      clearError();
      try {
        await versions.restore(productId, versionNumber);
        // Reload product data after restore.
        await refresh();
      } catch (err: unknown) {
        setError(
          err instanceof Error ? err.message : "Failed to restore version",
        );
        throw err;
      }
    },
    [productId, clearError, setError, refresh],
  );

  return {
    ...state,
    generate,
    addDocument,
    removeDocument,
    updateClaim,
    restoreVersion,
    refresh,
  };
}
