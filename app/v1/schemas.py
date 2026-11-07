from __future__ import annotations
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, ConfigDict, Field

class AddOnAttachment(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    itemId: Optional[str] = None
    dueTime: Optional[TimeOfDay] = None
    dueDate: Optional[Date] = None
    title: Optional[str] = None
    id: Optional[str] = None
    gradeSyncEnabled: Optional[bool] = None
    copyHistory: Optional[List[CopyHistory]] = None
    maxPoints: Optional[float] = None
    postId: Optional[str] = None
    courseId: Optional[str] = None
    studentViewUri: Optional[EmbedUri] = None
    teacherViewUri: Optional[EmbedUri] = None
    studentWorkReviewUri: Optional[EmbedUri] = None

class AddOnAttachmentStudentSubmission(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    userId: Optional[str] = None
    pointsEarned: Optional[float] = None
    courseWorkSubmissionId: Optional[str] = None
    postSubmissionState: Optional[str] = None

class AddOnContext(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    teacherContext: Optional[TeacherContext] = None
    studentContext: Optional[StudentContext] = None
    itemId: Optional[str] = None
    courseId: Optional[str] = None
    supportsStudentWork: Optional[bool] = None
    postId: Optional[str] = None

class Announcement(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    text: Optional[str] = None
    courseId: Optional[str] = None
    creatorUserId: Optional[str] = None
    individualStudentsOptions: Optional[IndividualStudentsOptions] = None
    alternateLink: Optional[str] = None
    creationTime: Optional[str] = None
    assigneeMode: Optional[str] = None
    id: Optional[str] = None
    materials: Optional[List[Material]] = None
    state: Optional[str] = None
    updateTime: Optional[str] = None
    scheduledTime: Optional[str] = None

class Assignment(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    studentWorkFolder: Optional[DriveFolder] = None

class AssignmentSubmission(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    attachments: Optional[List[Attachment]] = None

class Attachment(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    form: Optional[Form] = None
    link: Optional[Link] = None
    driveFile: Optional[DriveFile] = None
    youTubeVideo: Optional[YouTubeVideo] = None

class CloudPubsubTopic(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    topicName: Optional[str] = None

class CopyHistory(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    itemId: Optional[str] = None
    courseId: Optional[str] = None
    postId: Optional[str] = None
    attachmentId: Optional[str] = None

class Course(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    name: Optional[str] = None
    guardiansEnabled: Optional[bool] = None
    alternateLink: Optional[str] = None
    teacherGroupEmail: Optional[str] = None
    enrollmentCode: Optional[str] = None
    ownerId: Optional[str] = None
    courseMaterialSets: Optional[List[CourseMaterialSet]] = None
    courseState: Optional[str] = None
    description: Optional[str] = None
    subject: Optional[str] = None
    teacherFolder: Optional[DriveFolder] = None
    descriptionHeading: Optional[str] = None
    section: Optional[str] = None
    creationTime: Optional[str] = None
    courseGroupEmail: Optional[str] = None
    gradebookSettings: Optional[GradebookSettings] = None
    room: Optional[str] = None
    updateTime: Optional[str] = None
    calendarId: Optional[str] = None
    levels: Optional[str] = None

class CourseAlias(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    alias: Optional[str] = None

class CourseMaterial(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    form: Optional[Form] = None
    driveFile: Optional[DriveFile] = None
    link: Optional[Link] = None
    youTubeVideo: Optional[YouTubeVideo] = None

class CourseMaterialSet(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title: Optional[str] = None
    materials: Optional[List[CourseMaterial]] = None

class CourseRosterChangesInfo(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    courseId: Optional[str] = None

class CourseWork(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    submissionModificationMode: Optional[str] = None
    creationTime: Optional[str] = None
    dueDate: Optional[Date] = None
    updateTime: Optional[str] = None
    dueTime: Optional[TimeOfDay] = None
    assignment: Optional[Assignment] = None
    gradeCategory: Optional[GradeCategory] = None
    alternateLink: Optional[str] = None
    multipleChoiceQuestion: Optional[MultipleChoiceQuestion] = None
    creatorUserId: Optional[str] = None
    associatedWithDeveloper: Optional[bool] = None
    state: Optional[str] = None
    scheduledTime: Optional[str] = None
    topicId: Optional[str] = None
    maxPoints: Optional[float] = None
    assigneeMode: Optional[str] = None
    description: Optional[str] = None
    courseId: Optional[str] = None
    materials: Optional[List[Material]] = None
    individualStudentsOptions: Optional[IndividualStudentsOptions] = None
    id: Optional[str] = None
    gradingPeriodId: Optional[str] = None
    title: Optional[str] = None
    workType: Optional[str] = None

class CourseWorkChangesInfo(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    courseId: Optional[str] = None

class CourseWorkMaterial(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    topicId: Optional[str] = None
    state: Optional[str] = None
    description: Optional[str] = None
    id: Optional[str] = None
    individualStudentsOptions: Optional[IndividualStudentsOptions] = None
    creationTime: Optional[str] = None
    scheduledTime: Optional[str] = None
    courseId: Optional[str] = None
    title: Optional[str] = None
    materials: Optional[List[Material]] = None
    creatorUserId: Optional[str] = None
    assigneeMode: Optional[str] = None
    alternateLink: Optional[str] = None
    updateTime: Optional[str] = None

class Criterion(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    levels: Optional[List[Level]] = None
    id: Optional[str] = None
    description: Optional[str] = None
    title: Optional[str] = None

class Date(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    month: Optional[int] = None
    year: Optional[int] = None
    day: Optional[int] = None

class DriveFile(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    thumbnailUrl: Optional[str] = None
    id: Optional[str] = None
    alternateLink: Optional[str] = None
    title: Optional[str] = None

class DriveFolder(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    alternateLink: Optional[str] = None
    id: Optional[str] = None
    title: Optional[str] = None

class EmbedUri(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    uri: Optional[str] = None

class Empty(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    pass

class Feed(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    courseRosterChangesInfo: Optional[CourseRosterChangesInfo] = None
    courseWorkChangesInfo: Optional[CourseWorkChangesInfo] = None
    feedType: Optional[str] = None

class Form(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    responseUrl: Optional[str] = None
    title: Optional[str] = None
    formUrl: Optional[str] = None
    thumbnailUrl: Optional[str] = None

class GeminiGem(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None

class GlobalPermission(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    permission: Optional[str] = None

class GradeCategory(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: Optional[str] = None
    id: Optional[str] = None
    defaultGradeDenominator: Optional[int] = None
    weight: Optional[int] = None

class GradeHistory(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    gradeTimestamp: Optional[str] = None
    actorUserId: Optional[str] = None
    maxPoints: Optional[float] = None
    gradeChangeType: Optional[str] = None
    pointsEarned: Optional[float] = None

class GradebookSettings(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    calculationType: Optional[str] = None
    gradeCategories: Optional[List[GradeCategory]] = None
    displaySetting: Optional[str] = None

class GradingPeriod(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    startDate: Optional[Date] = None
    endDate: Optional[Date] = None
    title: Optional[str] = None

class GradingPeriodSettings(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    gradingPeriods: Optional[List[GradingPeriod]] = None
    applyToExistingCoursework: Optional[bool] = None

class Guardian(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    invitedEmailAddress: Optional[str] = None
    guardianId: Optional[str] = None
    guardianProfile: Optional[UserProfile] = None
    studentId: Optional[str] = None

class GuardianInvitation(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    state: Optional[str] = None
    invitedEmailAddress: Optional[str] = None
    studentId: Optional[str] = None
    creationTime: Optional[str] = None
    invitationId: Optional[str] = None

class IndividualStudentsOptions(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    studentIds: Optional[List[str]] = None

class Invitation(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    userId: Optional[str] = None
    role: Optional[str] = None
    courseId: Optional[str] = None

class Level(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    points: Optional[float] = None
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None

class Link(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    thumbnailUrl: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None

class ListAddOnAttachmentStudentSubmissionsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    addOnAttachmentStudentSubmissions: Optional[List[AddOnAttachmentStudentSubmission]] = None
    nextPageToken: Optional[str] = None

class ListAddOnAttachmentsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    addOnAttachments: Optional[List[AddOnAttachment]] = None
    nextPageToken: Optional[str] = None

class ListAnnouncementsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    nextPageToken: Optional[str] = None
    announcements: Optional[List[Announcement]] = None

class ListCourseAliasesResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    nextPageToken: Optional[str] = None
    aliases: Optional[List[CourseAlias]] = None

class ListCourseWorkMaterialResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    nextPageToken: Optional[str] = None
    courseWorkMaterial: Optional[List[CourseWorkMaterial]] = None

class ListCourseWorkResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    nextPageToken: Optional[str] = None
    courseWork: Optional[List[CourseWork]] = None

class ListCoursesResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    courses: Optional[List[Course]] = None
    nextPageToken: Optional[str] = None

class ListGuardianInvitationsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    guardianInvitations: Optional[List[GuardianInvitation]] = None
    nextPageToken: Optional[str] = None

class ListGuardiansResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    guardians: Optional[List[Guardian]] = None
    nextPageToken: Optional[str] = None

class ListInvitationsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    invitations: Optional[List[Invitation]] = None
    nextPageToken: Optional[str] = None

class ListRubricsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    nextPageToken: Optional[str] = None
    rubrics: Optional[List[Rubric]] = None

class ListStudentGroupMembersResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    studentGroupMembers: Optional[List[StudentGroupMember]] = None
    nextPageToken: Optional[str] = None

class ListStudentGroupsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    studentGroups: Optional[List[StudentGroup]] = None
    nextPageToken: Optional[str] = None

class ListStudentSubmissionsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    nextPageToken: Optional[str] = None
    studentSubmissions: Optional[List[StudentSubmission]] = None

class ListStudentsResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    students: Optional[List[Student]] = None
    nextPageToken: Optional[str] = None

class ListTeachersResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    nextPageToken: Optional[str] = None
    teachers: Optional[List[Teacher]] = None

class ListTopicResponse(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    nextPageToken: Optional[str] = None
    topic: Optional[List[Topic]] = None

class Material(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    form: Optional[Form] = None
    driveFile: Optional[SharedDriveFile] = None
    gem: Optional[GeminiGem] = None
    youtubeVideo: Optional[YouTubeVideo] = None
    link: Optional[Link] = None
    notebook: Optional[NotebookLmNotebook] = None

class ModifyAnnouncementAssigneesRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    modifyIndividualStudentsOptions: Optional[ModifyIndividualStudentsOptions] = None
    assigneeMode: Optional[str] = None

class ModifyAttachmentsRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    addAttachments: Optional[List[Attachment]] = None

class ModifyCourseWorkAssigneesRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    modifyIndividualStudentsOptions: Optional[ModifyIndividualStudentsOptions] = None
    assigneeMode: Optional[str] = None

class ModifyIndividualStudentsOptions(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    addStudentIds: Optional[List[str]] = None
    removeStudentIds: Optional[List[str]] = None

class MultipleChoiceQuestion(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    choices: Optional[List[str]] = None

class MultipleChoiceSubmission(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    answer: Optional[str] = None

class Name(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    familyName: Optional[str] = None
    fullName: Optional[str] = None
    givenName: Optional[str] = None

class NotebookLmNotebook(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title: Optional[str] = None
    id: Optional[str] = None
    url: Optional[str] = None

class ReclaimStudentSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    pass

class Registration(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    cloudPubsubTopic: Optional[CloudPubsubTopic] = None
    expiryTime: Optional[str] = None
    registrationId: Optional[str] = None
    feed: Optional[Feed] = None

class ReturnStudentSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    pass

class Rubric(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    courseId: Optional[str] = None
    sourceSpreadsheetId: Optional[str] = None
    updateTime: Optional[str] = None
    courseWorkId: Optional[str] = None
    creationTime: Optional[str] = None
    id: Optional[str] = None
    criteria: Optional[List[Criterion]] = None

class RubricGrade(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    levelId: Optional[str] = None
    criterionId: Optional[str] = None
    points: Optional[float] = None

class SharedDriveFile(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    shareMode: Optional[str] = None
    driveFile: Optional[DriveFile] = None

class ShortAnswerSubmission(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    answer: Optional[str] = None

class StateHistory(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    actorUserId: Optional[str] = None
    state: Optional[str] = None
    stateTimestamp: Optional[str] = None

class Student(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    profile: Optional[UserProfile] = None
    userId: Optional[str] = None
    studentWorkFolder: Optional[DriveFolder] = None
    courseId: Optional[str] = None

class StudentContext(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    submissionId: Optional[str] = None

class StudentGroup(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    courseId: Optional[str] = None
    title: Optional[str] = None

class StudentGroupMember(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    studentGroupId: Optional[str] = None
    userId: Optional[str] = None
    courseId: Optional[str] = None

class StudentSubmission(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    draftRubricGrades: Optional[Dict[str, Any]] = None
    alternateLink: Optional[str] = None
    assignmentSubmission: Optional[AssignmentSubmission] = None
    submissionHistory: Optional[List[SubmissionHistory]] = None
    courseWorkId: Optional[str] = None
    state: Optional[str] = None
    associatedWithDeveloper: Optional[bool] = None
    late: Optional[bool] = None
    updateTime: Optional[str] = None
    shortAnswerSubmission: Optional[ShortAnswerSubmission] = None
    assignedGrade: Optional[float] = None
    draftGrade: Optional[float] = None
    id: Optional[str] = None
    userId: Optional[str] = None
    multipleChoiceSubmission: Optional[MultipleChoiceSubmission] = None
    assignedRubricGrades: Optional[Dict[str, Any]] = None
    courseWorkType: Optional[str] = None
    creationTime: Optional[str] = None
    courseId: Optional[str] = None

class SubmissionHistory(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    stateHistory: Optional[StateHistory] = None
    gradeHistory: Optional[GradeHistory] = None

class Teacher(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    courseId: Optional[str] = None
    userId: Optional[str] = None
    profile: Optional[UserProfile] = None

class TeacherContext(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    pass

class TimeOfDay(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    seconds: Optional[int] = None
    hours: Optional[int] = None
    nanos: Optional[int] = None
    minutes: Optional[int] = None

class Topic(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    courseId: Optional[str] = None
    updateTime: Optional[str] = None
    topicId: Optional[str] = None
    name: Optional[str] = None

class TurnInStudentSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    pass

class UserProfile(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    verifiedTeacher: Optional[bool] = None
    id: Optional[str] = None
    photoUrl: Optional[str] = None
    permissions: Optional[List[GlobalPermission]] = None
    name: Optional[Name] = None
    emailAddress: Optional[str] = None

class YouTubeVideo(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    alternateLink: Optional[str] = None
    thumbnailUrl: Optional[str] = None
    title: Optional[str] = None
    id: Optional[str] = None
