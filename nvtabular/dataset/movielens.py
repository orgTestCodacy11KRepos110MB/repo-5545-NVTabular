import os

import cudf

from nvtabular import ops
from nvtabular.column_group import ColumnGroup, Tag
from nvtabular.dataset.base import ParquetPathCollection, TabularDataset
from nvtabular.io import Dataset
from nvtabular.utils import download_file


class MovieLens(TabularDataset):
    def __init__(self, work_dir, tokenizer=None, client_fn=None, test_size=0.1, random_state=42):
        super().__init__(os.path.join(work_dir, self.name()), client_fn=client_fn)
        self.csv_dir = os.path.join(self.data_dir, "ml-25m")

        self.test_size = test_size
        self.random_state = random_state
        self.tokenizer = tokenizer
        self.splits_dir = os.path.join(self.data_dir, "splits")
        if not os.path.exists(self.splits_dir):
            os.makedirs(self.splits_dir)

    def create_input_column_group(self):
        columns = ColumnGroup([])
        columns += ColumnGroup(["Title", "Review Text"], tags=Tag.TEXT)
        columns += ColumnGroup(
            ["Division Name", "Department Name", "Class Name", "Clothing ID"], tags=Tag.CATEGORICAL
        )
        columns += ColumnGroup(["Positive Feedback Count", "Age"], tags=Tag.CONTINUOUS)

        columns += (
            ColumnGroup(["Recommended IND"])
            >> ops.Rename(f=lambda x: x.replace(" IND", ""))
            >> ops.AddMetadata(tags=Tag.TARGETS_BINARY)
        )
        columns += ColumnGroup(["Rating"], tags=Tag.TARGETS_REGRESSION)

        return columns

    def create_default_transformations(self, data: ParquetPathCollection) -> ColumnGroup:
        user_id = ColumnGroup(["userId"], tags=Tag.USER)
        item_id = ColumnGroup(["movieId"], tags=Tag.ITEM)

        cat_features = (
            user_id + item_id
            >> ops.JoinExternal(data.parquet_files("movies"), on=["movieId"])
            >> ops.Categorify()
        )

        # Make rating a binary target
        rating_binary = (
            ColumnGroup(["rating"])
            >> (lambda col: (col > 3).astype("int8"))
            >> ops.Rename(postfix="_binary")
            >> ops.AddMetadata(is_binary_target=True)
        )

        rating = ColumnGroup(["rating"]) >> ops.AddMetadata(is_regression_target=True)

        return cat_features + rating + rating_binary

    def name(self) -> str:
        return "movielens"

    def prepare(self, frac_size=0.10) -> ParquetPathCollection:
        if not os.path.exists(self.csv_dir):
            zip_path = os.path.join(self.data_dir, "ml-25m.zip")
            download_file("http://files.grouplens.org/datasets/movielens/ml-25m.zip", zip_path)

        movies_path = os.path.join(self.splits_dir, "movies")

        train_path, eval_path = self.maybe_create_splits_with_cudf(
            input_dir=os.path.join(self.csv_dir, "ratings.csv"),
            output_dir=self.splits_dir,
            test_size=0.2,
        )

        if not os.path.exists(movies_path):
            movies = cudf.read_csv(os.path.join(self.csv_dir, "movies.csv"))
            movies["genres"] = movies["genres"].str.split("|")
            movies = movies.drop("title", axis=1)
            Dataset(movies).to_parquet(movies_path)

        return ParquetPathCollection(
            splits=ParquetPathCollection(train=train_path, eval=eval_path), movies=movies_path
        )
