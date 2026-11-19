"""TF-IDF text similarity between job descriptions and resume texts: the tie-breaker only (LLD §7.8, ADR-018).

The value is stored as `text_similarity` and shown separately. It is never part of the 0-100
score: it only orders pairs whose scores are exactly equal.

One TfidfVectorizer is fitted on all job descriptions and all resume texts of the match run.
Its rows are L2-normalized, so the dot product of two rows is their cosine similarity. A missing
or empty text has no terms and a similarity of 0 to everything.

Worker only: scikit-learn is installed in the worker image, not in the API image.
"""

from collections.abc import Sequence

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


class TextSimilarity:
    """Cosine similarity of each candidate's resume text to every job description."""

    def __init__(self, job_texts: Sequence[str | None], candidate_texts: Sequence[str | None]):
        self.job_count = len(job_texts)
        documents = [text or "" for text in [*job_texts, *candidate_texts]]
        self.document_count = len(documents)
        vectorizer = TfidfVectorizer(stop_words="english")
        try:
            matrix = vectorizer.fit_transform(documents)
        except ValueError:  # no document has a single usable word ("empty vocabulary")
            self._jobs = self._candidates = None
            self.vocabulary_size = 0
            return
        self._jobs = matrix[: self.job_count]
        self._candidates = matrix[self.job_count:]
        self.vocabulary_size = len(vectorizer.vocabulary_)

    def for_candidate(self, index: int) -> list[float]:
        """Similarity of candidate `index` to each job, in the order of `job_texts` (0 to 1)."""
        if self._jobs is None or self.job_count == 0:
            return [0.0] * self.job_count
        row = linear_kernel(self._candidates[index], self._jobs)[0]
        return [min(1.0, max(0.0, float(value))) for value in row]  # guard against rounding just outside [0, 1]
