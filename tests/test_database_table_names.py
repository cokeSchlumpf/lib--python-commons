from commons.database.entity import _entity_tablename
from commons.database.history import _history_tablename


def test_entity_table_name_of_a_word_ending_in_is():
    assert _entity_tablename("CaseAnalysisORM") == "case_analyses"


def test_history_table_name_of_a_word_ending_in_is():
    assert _history_tablename("CaseAnalysisHistoryORM") == "case_analyses_history"
