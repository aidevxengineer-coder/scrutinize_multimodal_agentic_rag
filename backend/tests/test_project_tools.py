import uuid
import pytest
from fastapi import HTTPException
from sqlmodel import Session, create_engine, SQLModel

from app.models.project import Project
from app.models.project_tool import ProjectTool
from app.schemas.v1.project_tool import ProjectToolCreate, ProjectToolUpdate
from app.services.project_tool_service import ProjectToolService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_and_get_project_tool(db_session: Session):
    project = Project(name="Test Proj", api_key="sk_test_123", client_key="pk_test_123")
    db_session.add(project)
    db_session.commit()

    service = ProjectToolService(db_session)
    create_dto = ProjectToolCreate(
        name="get_stock",
        display_name="Get Stock Count",
        description="Check live stock for SKU.",
        is_enabled=True,
        execution_mode="client_delegated",
        parameters_schema={
            "type": "object",
            "properties": {"sku": {"type": "string"}},
            "required": ["sku"],
        },
    )

    tool = service.create_tool(project.id, create_dto)
    assert tool.name == "get_stock"
    assert tool.project_id == project.id
    assert tool.is_enabled is True

    fetched = service.get_tool(project.id, tool.id)
    assert fetched.id == tool.id
    assert fetched.display_name == "Get Stock Count"


def test_invalid_tool_name_regex():
    with pytest.raises(ValueError):
        ProjectToolCreate(
            name="invalid name with spaces!",
            display_name="Invalid Tool",
            description="Test",
            parameters_schema={"type": "object"},
        )


def test_invalid_json_schema(db_session: Session):
    project = Project(name="Test Proj 2", api_key="sk_test_456", client_key="pk_test_456")
    db_session.add(project)
    db_session.commit()

    service = ProjectToolService(db_session)
    invalid_dto = ProjectToolCreate(
        name="invalid_schema_tool",
        display_name="Invalid Schema",
        description="Test schema failure",
        parameters_schema={"type": "invalid_type"},  # Invalid JSON Schema
    )

    with pytest.raises(HTTPException) as exc_info:
        service.create_tool(project.id, invalid_dto)
    assert exc_info.value.status_code == 400


def test_toggle_and_delete_tool(db_session: Session):
    project = Project(name="Test Proj 3", api_key="sk_test_789", client_key="pk_test_789")
    db_session.add(project)
    db_session.commit()

    service = ProjectToolService(db_session)
    tool = service.create_tool(
        project.id,
        ProjectToolCreate(
            name="tool_toggle",
            display_name="Toggle Me",
            description="Toggle description",
            parameters_schema={"type": "object"},
        ),
    )

    # Toggle off
    toggled = service.toggle_tool(project.id, tool.id, is_enabled=False)
    assert toggled.is_enabled is False

    active_tools = service.get_active_tools(project.id)
    assert len(active_tools) == 0

    # Delete
    service.delete_tool(project.id, tool.id)
    with pytest.raises(HTTPException):
        service.get_tool(project.id, tool.id)


def test_validate_arguments(db_session: Session):
    tool = ProjectTool(
        project_id=uuid.uuid4(),
        name="weather_check",
        display_name="Check Weather",
        description="Check weather forecast",
        parameters_schema={
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "days": {"type": "integer", "minimum": 1},
            },
            "required": ["location"],
        },
    )

    # Valid
    ProjectToolService.validate_arguments(tool, {"location": "London", "days": 3})

    # Invalid missing required argument
    with pytest.raises(ValueError):
        ProjectToolService.validate_arguments(tool, {"days": 3})
