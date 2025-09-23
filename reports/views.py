from django.shortcuts import render, get_object_or_404
from enactments.models import Batch, Enactment
from jobs.models import ProvisionJob
from defects.models import DefectLog, DefectCategory
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from django.db.models import Count, Sum
from openpyxl.utils import get_column_letter, range_boundaries
from django.utils import timezone 
from django.core.paginator import Paginator
from django.db.models import Q
 
def reports_view(request):
    batches = Batch.objects.all().order_by("-created_at")
    batch_id = request.GET.get("batch")
    search_query = request.GET.get("search", "")  # search input
    severity_filter = request.GET.get("severity", "")  # optional filter
 
    if batch_id:
        selected_batch = get_object_or_404(Batch, id=batch_id)
    else:
        selected_batch = batches.first()
 
    defects = DefectLog.objects.filter(
        provision_job__provision__batch=selected_batch,
        provision_job__status="completed",
        provision_job__is_generated = False
    ).order_by("id") if selected_batch else DefectLog.objects.none()
 
    # Apply search
    if search_query:
        defects = defects.filter(
            Q(issue_description__icontains=search_query) |
            Q(expected_outcome__icontains=search_query) |
            Q(actual_outcome__icontains=search_query) |
            Q(provision_job__provision__title__icontains=search_query) |
            Q(category__icontains=search_query) |
            Q(provision_job__enactment_assignment__enactment__title__icontains=search_query)
        )
 
    # Apply severity filter
    if severity_filter:
        defects = defects.filter(severity_level=severity_filter)
 
    # Pagination
    paginator = Paginator(defects, 10)  # 10 defects per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
 
    # Summary
    category_summary = {}
    for defect in defects:
        category_summary[defect.category] = category_summary.get(defect.category, 0) + 1
 
    context = {
        "batches": batches,
        "selected_batch": selected_batch,
        "enactments": Enactment.objects.filter(batch=selected_batch) if selected_batch else Enactment.objects.none(),
        "defects": page_obj,  # paginated
        "total_defects": defects.count(),
        "category_summary": category_summary,
        "search_query": search_query,
        "severity_filter": severity_filter,
        "active_page":"reports"
    }
    return render(request, "reports/index.html", context)
 
 
 
def partial_excel_report(request):
    batch_id = request.GET.get("batch")
    batch = get_object_or_404(Batch, id=batch_id)
    jobs = ProvisionJob.objects.filter(provision__batch=batch)

    return generate_excel_response(batch, f"Partial_Report_{batch.name}.xlsx", request)


def full_excel_report(request):
    batch_id = request.GET.get("batch")
    batch = get_object_or_404(Batch, id=batch_id)
    jobs = ProvisionJob.objects.filter(provision__batch=batch)
   
 
    # Check if all jobs are generated
    if not jobs.exists() or jobs.filter(is_generated=False).exists():
        return HttpResponse("Not all ProvisionJobs are generated for this batch.", status=400)
    return
    # return generate_excel_response(jobs, f"Full_Report_{batch.name}.xlsx")


def generate_excel_response(batch, filename, request = None):
    jobs = ProvisionJob.objects.filter(provision__batch = batch, status = "completed", is_generated=False).order_by("id")
    defects = DefectLog.objects.filter(provision_job__provision__batch=batch, provision_job__status = "completed", provision_job__is_generated = False).order_by("id")
    jobs_with_defects = jobs.annotate(
        defect_count=Count('defect_logs')
    ).filter(defect_count__gt=0).order_by("id")
 
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Defect Log"
 
 
 
    # Header
    headers = [
        "Defect ID",
        "Enactment Citation",
        "Provision Ref(s)",
        # "Version Date",
        "Category",
        "Check Type",
        "Issue Description",
        "Expected Outcome(BES)",
        "Actual Outcome(L+CP)",
        "Screenshot/Link",
        "Count per document",
        "Logged By",
        # "Date Logged",
        "Comments",
    ]
    ws1.append(headers)
 
    for defect in defects:
        url = ''
        if defect.screenshot:
            if request:
                url = defect.get_absolute_url(request)
        ws1.append([
            defect.id,
            defect.provision_job.enactment_assignment.enactment.title,
            defect.provision_job.provision.title,
            # defect.provision_job.date.strftime("%Y-%m-%d %H:%M"),
            defect.category,
            defect.check_type,
            defect.issue_description,
            defect.expected_outcome,
            defect.actual_outcome,
        
            url,
            defect.error_count,
            defect.provision_job.user.email,
            # defect.created_at,
            defect.comments
           
            ])
           
    ws2 = wb.create_sheet("Summary")
    ws2.merge_cells('B2:B3')
 
    ws2["B2"] = "Category"
    ws2["B2"].font = Font(size=12, bold=True)
    ws2["B2"].alignment = Alignment(horizontal='center', vertical='center')
    ws2["B2"].fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
 
 
    ws2.merge_cells('C2:C3')
    ws2["C2"] = "Error Type"
    ws2["C2"].font = Font(size=12, bold=True)
    ws2["C2"].alignment = Alignment(horizontal='center', vertical='center')
    ws2["C2"].fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
 
    ws2.merge_cells('D2:D3')
    ws2["D2"] = "Error Count"
    ws2["D2"].font = Font(size=12, bold=True)
    ws2["D2"].alignment = Alignment(horizontal='center', vertical='center')
    ws2["D2"].fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
 
    ws2.merge_cells('E2:E3')
    ws2["E2"] = "Error Rate"
    ws2["E2"].font = Font(size=12, bold=True)
    ws2["E2"].alignment = Alignment(horizontal='center', vertical='center')
    ws2["E2"].fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
 
    ws2.merge_cells('F2:I2')
    ws2["F2"] = "Error Count Per Type and Severity"
    ws2["F2"].alignment = Alignment(horizontal='center', vertical='center')
    ws2["F2"].fill = PatternFill(start_color="d5dce2", end_color="d5dce2", fill_type="solid")
 
    ws2["F3"] = "1"
    ws2["G3"] = "2"
    ws2["H3"] = "3"
    ws2["I3"] = "4"
 
    ws2.merge_cells('J2:K2')
    ws2["J2"] = "‘repeated issue’ trigger thresholds"
    ws2["J2"].alignment = Alignment(horizontal='center', vertical='center')
    ws2["J2"].fill = PatternFill(start_color="d5dce2", end_color="d5dce2", fill_type="solid")
    ws2["J3"] = "3"
    ws2["K3"] = "4"
    ws2["J3"].fill = PatternFill(start_color="d9e2f3", end_color="d9e2f3", fill_type="solid")
    ws2["K3"].fill = PatternFill(start_color="d9e2f3", end_color="d9e2f3", fill_type="solid")
 
    ws2["F3"].fill = PatternFill(start_color="d5dce2", end_color="d5dce2", fill_type="solid")
    ws2["G3"].fill = PatternFill(start_color="d5dce2", end_color="d5dce2", fill_type="solid")
    ws2["H3"].fill = PatternFill(start_color="d5dce2", end_color="d5dce2", fill_type="solid")
    ws2["I3"].fill = PatternFill(start_color="d5dce2", end_color="d5dce2", fill_type="solid")
 
    ws2["M4"] = f"% of Provisions with Error"
    ws2["M6"] = "Provisions with Error"
    ws2["M7"] = "Total Provisions"
 
    ws2["O6"] = jobs_with_defects.count()
    ws2["O7"] = jobs.count()
    ws2["O4"] = "=(O6/O7)"
    ws2["O4"].number_format = '0.00%'
 
 
 
    defect_categories = DefectCategory.objects.all()
    current_row = 4
    category_rows = []  # keep track of rows where categories are written
 
    severity_1_count = defects.filter(severity_level = 1).count()
    severity_2_count = defects.filter(severity_level = 2).count()
    severity_3_count = defects.filter(severity_level = 3).count()
    severity_4_count = defects.filter(severity_level = 4).count()
 
    job_rating0_count = jobs.filter(document_rating=0).count()
    job_rating1_count = jobs.filter(document_rating=1).count()
    job_rating2_count = jobs.filter(document_rating=2).count()
    job_rating3_count = jobs.filter(document_rating=3).count()
 
    block_ranges = ["B2:E3","F2:I3","J2:K3"]

    
    thinn_bottom = Side(style="double", color="000000")
 
    for category in defect_categories:
        error_count_value = defects.filter(category=category).count()
        ws2.cell(row=current_row, column=2, value=category.name)
        ws2.cell(row=current_row, column=4, value=int(error_count_value))
 
        category_rows.append(current_row)  # remember this row

        #change to bold
        for row in ws2[f"B{current_row}:K{current_row}"]:
            for cell in row:
                cell.font = Font(name="Times New Roman",size=12, bold=True)

                # preserve existing border
                current_border = cell.border

                cell.border = Border(
                    left=current_border.left,
                    right=current_border.right,
                    top=current_border.top,
                    bottom=thinn_bottom
                )



        

        block_cell = f"B{current_row}:"
        block_cell2 = f"F{current_row}:"
        block_cell3 = f"J{current_row}:"
 
       
 
        current_row += 1
        options = category.options.all()
 
        for option in options:

            defects_options = defects.filter(check_type=option.check_type)
            option_count = defects_options.count()
 
            ws2.cell(row=current_row, column=3, value=option.check_type)
            ws2.cell(row=current_row, column=4, value=option_count)


            ws2.cell(row=current_row, column=6, value=defects_options.filter(severity_level = 1).count())
            ws2.cell(row=current_row, column=7, value=defects_options.filter(severity_level = 2).count())
            ws2.cell(row=current_row, column=8, value=defects_options.filter(severity_level = 3).count())
            ws2.cell(row=current_row, column=9, value=defects_options.filter(severity_level = 4).count())
 
            ws2.cell(row=current_row, column=10, value=f"=(H{current_row}/O7)")
            ws2.cell(row=current_row, column=11, value=f"=(I{current_row}/O7)")
            ws2[f"J{current_row}"].number_format = "0.00%"
            ws2[f"K{current_row}"].number_format = "0.00%"
 
 
 
            current_row += 1
        current_row += 1
        block_cell += f"E{current_row}"
        block_cell2 += f"I{current_row}"
        block_cell3 += f"K{current_row}"
        block_ranges.append(block_cell)
        block_ranges.append(block_cell2)
        block_ranges.append(block_cell3)

 
    #Severity Table
    ws2["M10"] = "Severity"
    ws2["N10"] = "Level"
    ws2["O10"] = "Error Count"
    ws2["P10"] = "Error Rate"
 
    ws2["N11"] = 1
    ws2["N12"] = 2
    ws2["N13"] = 3
    ws2["N14"] = 4
    ws2["N15"] = "Total"
    ws2["M10"].fill = PatternFill(start_color="f7cbad", end_color="f7cbad", fill_type="solid")
    ws2["M11"].fill = PatternFill(start_color="f7cbad", end_color="f7cbad", fill_type="solid")
    ws2["M12"].fill = PatternFill(start_color="f7cbad", end_color="f7cbad", fill_type="solid")
    ws2["M13"].fill = PatternFill(start_color="f7cbad", end_color="f7cbad", fill_type="solid")
    ws2["M14"].fill = PatternFill(start_color="f7cbad", end_color="f7cbad", fill_type="solid")
    ws2["M15"].fill = PatternFill(start_color="f7cbad", end_color="f7cbad", fill_type="solid")
    ws2["O11"] = severity_1_count
    ws2["O12"] = severity_2_count
    ws2["O13"] = severity_3_count
    ws2["O14"] = severity_4_count
    ws2["O15"] = "=SUM(O11:O14)"
   
    ws2["P11"] = "=IFERROR(O11/$O$15,0)"
    ws2["P12"] = "=IFERROR(O12/$O$15,0)"
    ws2["P13"] = "=IFERROR(O13/$O$15,0)"
    ws2["P14"] = "=IFERROR(O14/$O$15,0)"
    ws2["P15"] = "=SUM(P11:P14)"
    ws2["P11"].number_format = '0.00%'
    ws2["P12"].number_format = '0.00%'
    ws2["P13"].number_format = '0.00%'
    ws2["P14"].number_format = '0.00%'
    ws2["P15"].number_format = '0.00%'
 
    #Quallity Table
    ws2["M17"] = "Quality"
    ws2["N17"] = "Rating"
    ws2["O17"] = "Rate Count"
    ws2["P17"] = "Percentage"
 
    ws2["N18"] = 0
    ws2["N19"] = 1
    ws2["N20"] = 2
    ws2["N21"] = 3
 
    ws2["N22"] = "Total"
 
    ws2["M17"].fill = PatternFill(start_color="e2efdb", end_color="e2efdb", fill_type="solid")
    ws2["M18"].fill = PatternFill(start_color="e2efdb", end_color="e2efdb", fill_type="solid")
    ws2["M19"].fill = PatternFill(start_color="e2efdb", end_color="e2efdb", fill_type="solid")
    ws2["M20"].fill = PatternFill(start_color="e2efdb", end_color="e2efdb", fill_type="solid")
    ws2["M21"].fill = PatternFill(start_color="e2efdb", end_color="e2efdb", fill_type="solid")
    ws2["M22"].fill = PatternFill(start_color="e2efdb", end_color="e2efdb", fill_type="solid")
 
    ws2["O18"] = job_rating0_count
    ws2["O19"] = job_rating1_count
    ws2["O20"] = job_rating2_count
    ws2["O21"] = job_rating3_count
    ws2["O22"] = "=SUM(O18:O21)"
   
    ws2["P18"] = "=IFERROR(O18/$O$22,0)"
    ws2["P19"] = "=IFERROR(O19/$O$22,0)"
    ws2["P20"] = "=IFERROR(O20/$O$22,0)"
    ws2["P21"] = "=IFERROR(O21/$O$22,0)"
    ws2["P22"] = "=SUM(P18:P21)"
 
    ws2["P18"].number_format = '0.00%'
    ws2["P19"].number_format = '0.00%'
    ws2["P20"].number_format = '0.00%'
    ws2["P21"].number_format = '0.00%'
    ws2["P22"].number_format = '0.00%'
   
 
 
 
   
 
   
 
    # Write TOTAL at the bottom
    total_row = current_row
    ws2.cell(row=total_row, column=2, value="TOTAL ERRORS")
 
    # Build SUM formula only for category rows
    sum_formula = "+".join([f"D{row}" for row in category_rows])
    ws2.cell(row=total_row, column=4, value=f"={sum_formula}")
 
    # Now go back and insert formulas referencing the total cell
    for row in category_rows:
        cell = ws2.cell(row=row, column=5, value=f"=IFERROR(D{row}/$D${total_row},0)")
        cell.number_format = '0.00%'
 
    ws2.sheet_view.showGridLines = False
 
 
    autofit_columns(ws1)
    # autofit_columns(ws2)
 
    #STYLING
    for block in block_ranges:
        add_outer_border(ws2, block, border_style="thick", color="000000")
 
 
    #summary sheet
    ws3 = wb.create_sheet("Enactments")
    headers = [
        "Filename",
        "Enactment Citation",
        "Provision",
        "Date \n (dd/mm/yyyy)",
        "Document rating",
        "Review Outcome",
        "Remarks"
    ]
    ws3.append(headers)
    for job in jobs:
        ws3.append([
            job.filename,
            job.enactment_assignment.enactment.title,
            job.provision.title,
            job.date,
            job.document_rating,
            "Defect Found DUmmyt",
            job.remarks
        ])

    #apply style
    for row in ws3[f"A1:H1"]:
            for cell in row:
                cell.font = Font(size=12, bold=True)
                cell.alignment = Alignment(horizontal='center', vertical='center')

    ws4 = wb.create_sheet("Error Type Highlights")
    ws4.merge_cells('B2:M4')
    ws4['B2'] = ">5 occurrences of the same Sev 3 issue in one document"
    ws4['B2'].alignment = Alignment(horizontal='left', vertical='center')

    table_headers = [
        "Defect ID",
        "Enactment Citation",
        "Provision Ref(s)",
        "Version Date",
        "Category",
        "Check Type",
        "Issue Description",
        "Expected Outcome (BES)",
        "Actual Outcome (L+CP)",
        "Screenshot / Link",
        "Severity",
        "Count per document"
    ]


    header_row = 5  # since merged block ends at row 4
    for col_index, header in enumerate(table_headers, start=2):  # B=2
        cell = ws4.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(name="Times New Roman", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.fill = PatternFill(start_color="D5DCE2", end_color="D5DCE2", fill_type="solid")


    #>5 error count of the same Sev 3 issue in one document
    greater_five_severity3_defects = defects.filter(severity_level=3, error_count__gt=5)
    data_start_row = header_row + 1
    for i, defect in enumerate(greater_five_severity3_defects):
        row_index = data_start_row + i
        ws4.cell(row=row_index, column=2, value=defect.id)
        ws4.cell(row=row_index, column=3, value=defect.provision_job.provision.enactment.title)
        ws4.cell(row=row_index, column=4, value=defect.provision_job.provision.title)
        ws4.cell(row=row_index, column=5, value=defect.provision_job.date)
        ws4.cell(row=row_index, column=6, value=defect.category)
        ws4.cell(row=row_index, column=7, value=defect.check_type)
        ws4.cell(row=row_index, column=8, value=defect.issue_description)
        ws4.cell(row=row_index, column=9, value=defect.expected_outcome)
        ws4.cell(row=row_index, column=10, value=defect.actual_outcome)
        ws4.cell(row=row_index, column=11, value=defect.get_absolute_url(request))
        ws4.cell(row=row_index, column=12, value=defect.severity_level)
        ws4.cell(row=row_index, column=13, value=defect.error_count)

    # Define thin and thick sides
    thin_side = Side(border_style="thin", color="000000")
    thick_side = Side(border_style="thick", color="000000")

    # Determine the full block range
    start_row = 2
    end_row = data_start_row + len(greater_five_severity3_defects) - 1
    start_col = 2  # B
    end_col = 13   # M

    # Apply thick outer border
    for row in range(start_row, end_row + 1):
        for col in range(start_col, end_col + 1):
            cell = ws4.cell(row=row, column=col)
            left   = thick_side if col == start_col else None
            right  = thick_side if col == end_col else None
            top    = thick_side if row == start_row else None
            bottom = thick_side if row == end_row else None
            current = cell.border
            cell.border = Border(
                left=left or current.left,
                right=right or current.right,
                top=top or current.top,
                bottom=bottom or current.bottom
            )

    # Apply thin inner borders (title + headers + data)
    for row in range(start_row, end_row + 1):
        for col in range(start_col, end_col + 1):
            cell = ws4.cell(row=row, column=col)
            current = cell.border
            cell.border = Border(
                left=current.left or thin_side,
                right=current.right or thin_side,
                top=current.top or thin_side,
                bottom=current.bottom or thin_side
            )

    # ========================
    # SECOND TABLE (Sev 4 > 10)
    # ========================

    # Skip 1 row after first table
    second_title_row = end_row + 2
    second_header_row = second_title_row + 3

    ws4.merge_cells(start_row=second_title_row, start_column=2, end_row=second_title_row+2, end_column=13)
    ws4.cell(row=second_title_row, column=2, value=">10 occurrences of the same Sev 4 issue in one document").alignment = Alignment(horizontal='left', vertical='center')

    # Headers
    for col_index, header in enumerate(table_headers, start=2):
        cell = ws4.cell(row=second_header_row, column=col_index, value=header)
        cell.font = Font(name="Times New Roman", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.fill = PatternFill(start_color="D5DCE2", end_color="D5DCE2", fill_type="solid")

    greater_10_severity4_defects = defects.filter(severity_level=4, error_count__gt=10)

    data_start_row_2 = second_header_row + 1
    for i, defect in enumerate(greater_10_severity4_defects):
        row_index = data_start_row_2 + i
        ws4.cell(row=row_index, column=2, value=defect.id)
        ws4.cell(row=row_index, column=3, value=defect.provision_job.provision.enactment.title)
        ws4.cell(row=row_index, column=4, value=defect.provision_job.provision.title)
        ws4.cell(row=row_index, column=5, value=defect.provision_job.date)
        ws4.cell(row=row_index, column=6, value=defect.category)
        ws4.cell(row=row_index, column=7, value=defect.check_type)
        ws4.cell(row=row_index, column=8, value=defect.issue_description)
        ws4.cell(row=row_index, column=9, value=defect.expected_outcome)
        ws4.cell(row=row_index, column=10, value=defect.actual_outcome)
        ws4.cell(row=row_index, column=11, value=defect.get_absolute_url(request))
        ws4.cell(row=row_index, column=12, value=defect.severity_level)
        ws4.cell(row=row_index, column=13, value=defect.error_count)

    # Borders for table 2
    start_row_2 = second_title_row
    end_row_2 = data_start_row_2 + len(greater_10_severity4_defects) - 1

    for row in range(start_row_2, end_row_2 + 1):
        for col in range(start_col, end_col + 1):
            cell = ws4.cell(row=row, column=col)
            left   = thick_side if col == start_col else None
            right  = thick_side if col == end_col else None
            top    = thick_side if row == start_row_2 else None
            bottom = thick_side if row == end_row_2 else None
            current = cell.border
            cell.border = Border(
                left=left or current.left,
                right=right or current.right,
                top=top or current.top,
                bottom=bottom or current.bottom
            )

    for row in range(start_row_2, end_row_2 + 1):
        for col in range(start_col, end_col + 1):
            cell = ws4.cell(row=row, column=col)
            current = cell.border
            cell.border = Border(
                left=current.left or thin_side,
                right=current.right or thin_side,
                top=current.top or thin_side,
                bottom=current.bottom or thin_side
            )

    ws4.sheet_view.showGridLines = False

    



    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is not None:
                    current = cell.font
                    cell.font = Font(
                        name="Times New Roman",
                        size=current.size if current.size else 12,
                        bold=current.bold,
                        italic=current.italic,
                        underline=current.underline,
                        strike=current.strike,
                        color=current.color
                    )
    # Response
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)

    autofit_columns(ws1)
    autofit_columns(ws3)
    autofit_columns(ws4)


    #set jobs generated
    for job in jobs:
        job.is_generated = True
        job.generation_date = timezone.now()
        job.save()


    

    return response
 
 
def autofit_columns(ws):
    for col in ws.columns:
        column = col[0].column  # column number
        if 6 <= column <= 9:    # skip columns F to I
            continue
 
        max_length = 0
        column_letter = get_column_letter(column)
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[column_letter].width = max_length + 2

def add_outer_border(ws, cell_range, border_style="thin", color="000000"):
    """
    Apply an outer border around a range (like a rectangle) without overriding existing borders.
    
    :param ws: Worksheet
    :param cell_range: Excel range string (e.g., "B2:I3")
    :param border_style: Border style (default "thin")
    :param color: Border color (default black)
    """
    side = Side(border_style=border_style, color=color)
    min_col, min_row, max_col, max_row = range_boundaries(cell_range)

    for row in range(min_row, max_row + 1):
        for col in range(min_col, max_col + 1):
            cell = ws.cell(row=row, column=col)
            
            # Get the current border of the cell
            current = cell.border

            # Only override sides if we are on the edge
            left   = side if col == min_col else current.left
            right  = side if col == max_col else current.right
            top    = side if row == min_row else current.top
            bottom = side if row == max_row else current.bottom

            # Reassign border while preserving non-edge sides
            cell.border = Border(left=left, right=right, top=top, bottom=bottom)