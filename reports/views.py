from django.shortcuts import render, get_object_or_404
from enactments.models import Batch, Enactment
from jobs.models import ProvisionJob
from defects.models import DefectLog, DefectCategory
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from django.db.models import Count, Sum
from openpyxl.utils import get_column_letter, range_boundaries


def reports_view(request):
    batches = Batch.objects.all().order_by("-created_at")  # newest first
    batch_id = request.GET.get("batch")

    if batch_id:
        selected_batch = get_object_or_404(Batch, id=batch_id)
    else:
        selected_batch = batches.first()  # ✅ default to latest batch

    enactments = Enactment.objects.filter(batch=selected_batch) if selected_batch else Enactment.objects.none()
    defects = DefectLog.objects.filter(provision_job__provision__batch=selected_batch) if selected_batch else DefectLog.objects.none()

    # Summary
    category_summary = {}
    for defect in defects:
        category_summary[defect.category] = category_summary.get(defect.category, 0) + 1

    context = {
        "batches": batches,
        "selected_batch": selected_batch,
        "enactments": enactments,
        "defects": defects,
        "total_defects": defects.count(),
        "category_summary": category_summary,
    }
    return render(request, "reports/index.html", context)


def partial_excel_report(request):
    batch_id = request.GET.get("batch")
    batch = get_object_or_404(Batch, id=batch_id)
    jobs = ProvisionJob.objects.filter(provision__batch=batch)

    return generate_excel_response(batch, f"Partial_Report_{batch.name}.xlsx")


def full_excel_report(request):
    batch_id = request.GET.get("batch")
    batch = get_object_or_404(Batch, id=batch_id)
    jobs = ProvisionJob.objects.filter(provision__batch=batch)
    

    # Check if all jobs are generated
    if not jobs.exists() or jobs.filter(is_generated=False).exists():
        return HttpResponse("Not all ProvisionJobs are generated for this batch.", status=400)
    return
    # return generate_excel_response(jobs, f"Full_Report_{batch.name}.xlsx")


def generate_excel_response(batch, filename):
    jobs = ProvisionJob.objects.filter(provision__batch = batch, status = "completed")
    defects = DefectLog.objects.filter(provision_job__provision__batch=batch, provision_job__status = "completed")
    jobs_with_defects = ProvisionJob.objects.annotate(
        defect_count=Count('defect_logs')
    ).filter(defect_count__gt=0)

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

        "Link",
        "Count per document",
        "Logged By",
        # "Date Logged",
        "Comments",
    ]
    ws1.append(headers)

    for defect in defects:

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
        
            defect.link,
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

    block_ranges = ["B2:I3",]

    for category in defect_categories:
        error_count_value = defects.filter(category=category).count()
        ws2.cell(row=current_row, column=2, value=category.name)
        ws2.cell(row=current_row, column=4, value=int(error_count_value))

        category_rows.append(current_row)  # remember this row

        

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
    autofit_columns(ws2)

    #STYLING
    add_outer_border(ws2, "B2:I3", border_style="thick", color="000000")






    
    





    



    # Response
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
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
    Apply an outer border around a range (like a rectangle).
    
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

            left   = side if col == min_col else None
            right  = side if col == max_col else None
            top    = side if row == min_row else None
            bottom = side if row == max_row else None

            cell.border = Border(left=left, right=right, top=top, bottom=bottom)